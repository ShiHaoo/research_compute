import pytest

import app.db as db


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    yield


def test_session_and_message_roundtrip():
    sid = db.create_session("hello")
    db.add_message(sid, "user", "hi", None)
    db.add_message(
        sid,
        "assistant",
        "yo",
        '[{"id":"c1","name":"job_status","arguments":"{}","result":"ok"}]',
    )
    msgs = db.list_messages(sid)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["tool_calls"].startswith("[{")


def test_list_sessions_newest_first():
    a = db.create_session("first")
    b = db.create_session("second")
    assert [s["id"] for s in db.list_sessions()] == [b, a]


def test_rename_session():
    sid = db.create_session("old")
    db.rename_session(sid, "new")
    titles = {s["id"]: s["title"] for s in db.list_sessions()}
    assert titles[sid] == "new"


def test_job_roundtrip():
    db.insert_job("j1", "seq_stats", "sample1.fasta", "running", "a.log", "b.log")
    assert db.get_job("j1")["status"] == "running"
    assert db.get_job("j1")["exit_code"] is None
    db.update_job("j1", status="success", exit_code=0)
    assert db.get_job("j1")["status"] == "success"
    assert db.get_job("j1")["exit_code"] == 0


def test_get_job_missing_returns_none():
    assert db.get_job("nope") is None
