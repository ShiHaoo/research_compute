"""三个工具：submit_job / job_status / read_log，供 Agent 循环调用。"""
from app import jobs

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "submit_job",
            "description": "提交一个序列分析任务（seq_stats 或 find_orf），在后台异步运行，返回任务 ID。",
            "parameters": {
                "type": "object",
                "properties": {
                    "analysis_type": {"type": "string", "enum": ["seq_stats", "find_orf"]},
                    "filename": {"type": "string", "description": "data/ 目录下的 FASTA 文件名，如 sample1.fasta"},
                },
                "required": ["analysis_type", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "job_status",
            "description": "按任务 ID 查询状态（running / success / failed）。",
            "parameters": {
                "type": "object",
                "properties": {"job_id": {"type": "string"}},
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_log",
            "description": "按任务 ID 读取 stdout/stderr 日志（过长会自动截断）。任务失败时用它查看原因。",
            "parameters": {
                "type": "object",
                "properties": {"job_id": {"type": "string"}},
                "required": ["job_id"],
            },
        },
    },
]


async def submit_job(analysis_type: str, filename: str) -> str:
    job_id = await jobs.submit_job(analysis_type, filename)
    return f"任务已提交，job_id={job_id}（任务约几秒完成，请调用 job_status 轮询状态）"


async def job_status(job_id: str) -> str:
    s = jobs.get_status(job_id)
    if s == "not_found":
        return "未找到该任务"
    return f"状态：{s}"


async def read_log(job_id: str) -> str:
    if jobs.get_status(job_id) == "not_found":
        return "未找到该任务"
    logs = jobs.read_logs(job_id)
    return f"stdout:\n{logs['stdout']}\nstderr:\n{logs['stderr']}"


TOOL_HANDLERS: dict[str, object] = {
    "submit_job": submit_job,
    "job_status": job_status,
    "read_log": read_log,
}
