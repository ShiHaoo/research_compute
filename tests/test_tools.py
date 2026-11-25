import asyncio

import pytest

import app.db as db
import app.jobs as jobs
import app.tools as tools


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    yield


def test_submit_job_rejects_bad_input():
    with pytest.raises(ValueError):
        asyncio.run(tools.submit_job("nope", "sample1.fasta"))
    with pytest.raises(ValueError):
        asyncio.run(tools.submit_job("seq_stats", "missing.fasta"))


def test_submit_job_wraps_result(monkeypatch):
    async def fake_submit(analysis_type, filename):
        return "abc123"

    monkeypatch.setattr(jobs, "submit_job", fake_submit)
    result = asyncio.run(tools.submit_job("seq_stats", "sample1.fasta"))
    assert "job_id=abc123" in result
    assert "job_status" in result


def test_tools_unknown_job():
    assert asyncio.run(tools.job_status("nope")) == "未找到该任务"
    assert asyncio.run(tools.read_log("nope")) == "未找到该任务"


def test_read_log_truncates(tmp_path):
    out = tmp_path / "long.log"
    out.write_text("A" * 5000, encoding="utf-8")
    db.insert_job("j3", "seq_stats", "s.fasta", "success", str(out), str(tmp_path / "e.log"))
    result = asyncio.run(tools.read_log("j3"))
    assert "...(truncated)" in result
    assert "stdout:" in result
    assert "stderr:" in result


def test_tool_schemas_are_consistent():
    names = [t["function"]["name"] for t in tools.TOOLS]
    assert names == ["submit_job", "job_status", "read_log"]
    assert set(tools.TOOL_HANDLERS.keys()) == set(names)
