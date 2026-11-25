import pytest
from fastapi.testclient import TestClient

import app.db as db
import app.main as main
import app.tools as tools


class FakeLLM:
    def __init__(self, script):
        self.script = script
        self.i = 0

    async def stream_chat(self, messages, tools):
        idx = min(self.i, len(self.script) - 1)
        self.i += 1
        for item in self.script[idx]:
            yield item


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    yield


def test_sessions_crud():
    with TestClient(main.app) as client:
        r = client.post("/api/sessions", json={"title": "hi"})
        assert r.status_code == 200
        sid = r.json()["id"]
        assert sid in [s["id"] for s in client.get("/api/sessions").json()["sessions"]]
        assert client.get(f"/api/sessions/{sid}/messages").json()["messages"] == []


def test_chat_streams_tokens(monkeypatch):
    monkeypatch.setattr(main, "get_llm", lambda: FakeLLM(
        [[{"kind": "delta", "content": "你好"}, {"kind": "delta", "content": "！"}]]
    ))
    with TestClient(main.app) as client:
        sid = client.post("/api/sessions", json={}).json()["id"]
        body = client.post("/api/chat", json={"session_id": sid, "message": "hi"}).text
        assert "event: token" in body
        assert "event: done" in body
        assert "你好" in body


def test_chat_streams_tool_calls(monkeypatch):
    async def fake_submit(analysis_type, filename):
        return "任务已提交，job_id=job1"

    monkeypatch.setitem(tools.TOOL_HANDLERS, "submit_job", fake_submit)
    monkeypatch.setattr(main, "get_llm", lambda: FakeLLM([
        [{"kind": "tool_calls", "tool_calls": [
            {"id": "c1", "name": "submit_job",
             "arguments": '{"analysis_type":"seq_stats","filename":"sample1.fasta"}'},
        ]}],
        [{"kind": "delta", "content": "已提交。"}],
    ]))
    with TestClient(main.app) as client:
        sid = client.post("/api/sessions", json={}).json()["id"]
        body = client.post("/api/chat", json={"session_id": sid, "message": "统计"}).text
        assert "event: tool_call" in body
        assert "submit_job" in body
        assert "event: token" in body

        msgs = client.get(f"/api/sessions/{sid}/messages").json()["messages"]
        assert [m["role"] for m in msgs] == ["user", "assistant", "assistant"]
        assert msgs[1]["tool_calls"][0]["name"] == "submit_job"
