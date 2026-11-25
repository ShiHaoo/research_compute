import asyncio
import sys

import pytest

import app.db as db
import app.jobs as jobs


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    yield


def _write_script(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_execute_success_and_failure(tmp_path):
    ok = _write_script(tmp_path, "ok.py", "print('hello')\n")
    fail = _write_script(tmp_path, "fail.py", "import sys; sys.stderr.write('boom'); sys.exit(1)\n")
    out1 = tmp_path / "ok.stdout.log"
    err1 = tmp_path / "ok.stderr.log"
    out2 = tmp_path / "fail.stdout.log"
    err2 = tmp_path / "fail.stderr.log"

    db.insert_job("j1", "seq_stats", "s.fasta", "running", str(out1), str(err1))
    db.insert_job("j2", "seq_stats", "s.fasta", "running", str(out2), str(err2))

    asyncio.run(jobs.execute("j1", [sys.executable, str(ok)], str(out1), str(err1)))
    asyncio.run(jobs.execute("j2", [sys.executable, str(fail)], str(out2), str(err2)))

    assert db.get_job("j1")["status"] == "success"
    assert db.get_job("j1")["exit_code"] == 0
    assert db.get_job("j2")["status"] == "failed"
    assert db.get_job("j2")["exit_code"] == 1
    assert err2.read_text(encoding="utf-8") == "boom"
    assert out1.read_text(encoding="utf-8") == "hello\n"


def test_resolve_script():
    assert jobs.resolve_script("seq_stats") == "scripts.seq_stats"
    assert jobs.resolve_script("find_orf") == "scripts.find_orf"
    with pytest.raises(ValueError):
        jobs.resolve_script("nope")


def test_get_status():
    db.insert_job("j4", "seq_stats", "s.fasta", "running", "a", "b")
    assert jobs.get_status("j4") == "running"
    assert jobs.get_status("missing") == "not_found"


def test_read_logs_truncates(tmp_path):
    out = tmp_path / "long.log"
    out.write_text("A" * 5000, encoding="utf-8")
    db.insert_job("j3", "seq_stats", "s.fasta", "success", str(out), str(tmp_path / "e.log"))
    logs = jobs.read_logs("j3", max_chars=4000)
    assert logs["stdout"] == "A" * 4000 + "...(truncated)"
