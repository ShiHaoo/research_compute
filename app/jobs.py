"""后台任务运行器：以子进程执行分析脚本，日志落盘，状态存库。

Ruling: 用 ``python -m scripts.<type>`` 而非 ``python scripts/<type>.py`` 启动脚本，
这样脚本内部的 ``from scripts.fasta_utils import ...`` 绝对导入在两种场景（被 pytest
import、被子进程 -m 运行）都能解析；代价是子进程 cwd 必须是项目根（这里显式传 cwd）。
同时设 ``PYTHONUTF8=1``，保证子进程 stdout/stderr 以 UTF-8 落盘，read_logs 按 UTF-8 读回。
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.config import load_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SCRIPTS = {
    "seq_stats": "scripts.seq_stats",
    "find_orf": "scripts.find_orf",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_script(analysis_type: str) -> str:
    if analysis_type not in SCRIPTS:
        raise ValueError(f"未知分析类型: {analysis_type}")
    return SCRIPTS[analysis_type]


def _abs(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    return env


async def execute(job_id: str, cmd: list[str], stdout_path: str, stderr_path: str) -> None:
    with open(stdout_path, "wb") as out, open(stderr_path, "wb") as err:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=out,
            stderr=err,
            cwd=str(PROJECT_ROOT),
            env=_subprocess_env(),
        )
        returncode = await proc.wait()
    db.update_job(
        job_id,
        status="success" if returncode == 0 else "failed",
        exit_code=returncode,
        finished_at=_now(),
    )


async def submit_job(analysis_type: str, filename: str) -> str:
    module = resolve_script(analysis_type)
    cfg = load_config()
    data_file = _abs(cfg.data_dir) / filename
    if not data_file.is_file():
        raise ValueError(f"文件不存在: {filename}")

    logs_dir = _abs(cfg.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex
    stdout_path = logs_dir / f"{job_id}.stdout.log"
    stderr_path = logs_dir / f"{job_id}.stderr.log"

    db.insert_job(job_id, analysis_type, filename, "running", str(stdout_path), str(stderr_path))
    cmd = [sys.executable, "-m", module, str(data_file)]
    asyncio.create_task(execute(job_id, cmd, str(stdout_path), str(stderr_path)))
    return job_id


def get_status(job_id: str) -> str:
    job = db.get_job(job_id)
    if job is None:
        return "not_found"
    return job["status"]


def _truncate(text: str, max_chars: int) -> str:
    if len(text) > max_chars:
        return text[:max_chars] + "...(truncated)"
    return text


def read_logs(job_id: str, max_chars: int = 4000) -> dict:
    job = db.get_job(job_id)
    if job is None:
        return {"stdout": "", "stderr": ""}

    def read(path: str | None) -> str:
        if path and Path(path).is_file():
            return Path(path).read_text(encoding="utf-8", errors="replace")
        return ""

    return {
        "stdout": _truncate(read(job.get("stdout_path")), max_chars),
        "stderr": _truncate(read(job.get("stderr_path")), max_chars),
    }
