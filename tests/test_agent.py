import asyncio
import json

import app.db as db
import app.tools as tools
from app import agent


class FakeLLM:
    def __init__(self, script):
        self.script = script
        self.i = 0

    async def stream_chat(self, messages, tools):
        idx = min(self.i, len(self.script) - 1)
        self.i += 1
        for item in self.script[idx]:
            yield item


SUCCESS_SCRIPT = [
    [{"kind": "tool_calls", "tool_calls": [
        {"id": "c1", "name": "submit_job",
         "arguments": '{"analysis_type":"seq_stats","filename":"sample1.fasta"}'},
    ]}],
    [{"kind": "tool_calls", "tool_calls": [
        {"id": "c2", "name": "job_status", "arguments": '{"job_id":"job1"}'},
    ]}],
    [{"kind": "tool_calls", "tool_calls": [
        {"id": "c3", "name": "job_status", "arguments": '{"job_id":"job1"}'},
    ]}],
    [{"kind": "tool_calls", "tool_calls": [
        {"id": "c4", "name": "read_log", "arguments": '{"job_id":"job1"}'},
    ]}],
    [{"kind": "delta", "content": "sample1 共 2 条序列。"},
     {"kind": "delta", "content": " 长度和 GC 如下。"}],
]


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    sid = db.create_session("t")
    db.add_message(sid, "user", "统计 sample1 GC", None)
    return sid


def test_agent_success_path(monkeypatch, tmp_path):
    sid = _setup(tmp_path, monkeypatch)

    async def fake_submit(analysis_type, filename):
        return "任务已提交，job_id=job1"

    async def fake_status(job_id):
        return "状态：success"

    async def fake_read(job_id):
        return "stdout:\nseq1\t45\t48.89%\n"

    monkeypatch.setitem(tools.TOOL_HANDLERS, "submit_job", fake_submit)
    monkeypatch.setitem(tools.TOOL_HANDLERS, "job_status", fake_status)
    monkeypatch.setitem(tools.TOOL_HANDLERS, "read_log", fake_read)

    events = []

    async def send(event, data):
        events.append((event, data))

    asyncio.run(agent.run_agent(sid, FakeLLM(SUCCESS_SCRIPT), send))

    tool_names = [d["name"] for e, d in events if e == "tool_call"]
    assert tool_names == ["submit_job", "job_status", "job_status", "read_log"]
    assert any(e == "token" for e, _ in events)
    assert events[-1][0] == "done"

    msgs = db.list_messages(sid)
    assert [m["role"] for m in msgs] == ["user"] + ["assistant"] * 5
    assert msgs[-1]["content"] == "sample1 共 2 条序列。 长度和 GC 如下。"


def test_agent_failure_path_reads_log(monkeypatch, tmp_path):
    sid = _setup(tmp_path, monkeypatch)

    async def fake_submit(analysis_type, filename):
        return "任务已提交，job_id=job2"

    async def fake_status(job_id):
        return "状态：failed"

    async def fake_read(job_id):
        return "stderr:\nFASTA 解析失败：缺少 '>' 标题行"

    monkeypatch.setitem(tools.TOOL_HANDLERS, "submit_job", fake_submit)
    monkeypatch.setitem(tools.TOOL_HANDLERS, "job_status", fake_status)
    monkeypatch.setitem(tools.TOOL_HANDLERS, "read_log", fake_read)

    script = [
        [{"kind": "tool_calls", "tool_calls": [
            {"id": "c1", "name": "submit_job",
             "arguments": '{"analysis_type":"seq_stats","filename":"sample3.fasta"}'},
        ]}],
        [{"kind": "tool_calls", "tool_calls": [
            {"id": "c2", "name": "job_status", "arguments": '{"job_id":"job2"}'},
        ]}],
        [{"kind": "tool_calls", "tool_calls": [
            {"id": "c3", "name": "read_log", "arguments": '{"job_id":"job2"}'},
        ]}],
        [{"kind": "delta", "content": "任务失败了，因为文件缺少 '>' 标题行。"}],
    ]

    events = []

    async def send(event, data):
        events.append((event, data))

    asyncio.run(agent.run_agent(sid, FakeLLM(script), send))

    tool_names = [d["name"] for e, d in events if e == "tool_call"]
    assert tool_names == ["submit_job", "job_status", "read_log"]
    assert events[-1][0] == "done"


def test_reconstructs_tool_messages(monkeypatch, tmp_path):
    sid = _setup(tmp_path, monkeypatch)
    db.add_message(sid, "assistant", "", json.dumps([
        {"id": "c1", "name": "job_status", "arguments": {"job_id": "j"}, "result": "状态：success"},
        {"id": "c2", "name": "read_log", "arguments": {"job_id": "j"}, "result": "stdout:..."},
    ]))

    msgs = agent.build_messages(sid)
    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    assert len(tool_msgs) == 2
    assert tool_msgs[0]["tool_call_id"] == "c1"
    assert tool_msgs[0]["content"] == "状态：success"

    asst = [m for m in msgs if m["role"] == "assistant" and m.get("tool_calls")]
    assert len(asst) == 1
    assert asst[0]["tool_calls"][0]["function"]["name"] == "job_status"
    assert json.loads(asst[0]["tool_calls"][0]["function"]["arguments"]) == {"job_id": "j"}
