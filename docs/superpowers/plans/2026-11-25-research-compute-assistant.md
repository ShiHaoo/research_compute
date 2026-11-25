# 科研计算任务助手 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付一个本机可跑的全栈智能体：FastAPI 后端跑「思考→调工具→继续思考」循环，原生 JS 前端流式展示回复与工具调用，SQLite 持久化会话，两个 Python 子进程分析脚本（seq_stats / find_orf）。

**Architecture:** 单进程 FastAPI 服务，同时托管 API 与静态前端。`agent.py` 用 DeepSeek（OpenAI 兼容）流式调用实现工具循环，经 SSE 把文本增量与工具事件推给前端；`jobs.py` 用 `asyncio.create_subprocess_exec` 后台跑 `scripts/*.py`，日志落盘；`db.py`（sqlite3 标准库）持久化 sessions/messages/jobs。

**Tech Stack:** Python 3.12、FastAPI、uvicorn、openai SDK（指向 DeepSeek）、python-dotenv、sqlite3、pytest；前端原生 HTML/JS/CSS（无构建步骤）。

**Spec:** [docs/superpowers/specs/2026-11-25-research-compute-assistant-design.md](../specs/2026-11-25-research-compute-assistant-design.md)

## Global Constraints

- Python 3.12；依赖仅 `fastapi uvicorn[standard] openai python-dotenv`，测试用 `pytest httpx`。
- 后端语言 Python，前端原生 JS（无 node 构建）。
- DeepSeek：`LLM_BASE_URL` 默认 `https://api.deepseek.com`，`LLM_MODEL` 默认 `deepseek-chat`；key 从 `.env` 读，`.env` 进 `.gitignore`。
- FASTA 序列合法字符仅 `A/C/G/T/N`（大小写不敏感）；非法字符（如 `X`、数字）→ 报错。
- 分析脚本仅在 `__main__` 路径 sleep 3–5 秒；被 `import` 时不 sleep（便于测试）。
- ORF 定义为「完整 ORF」：`ATG` 起始 + 同读框内首个终止子（`TAA/TAG/TGA`）；只搜正链三个读框；无完整 ORF 返回 `None`。位置 1-based，终止位置含终止子。
- 日志截断阈值 4000 字符；超阈值加 `...(truncated)` 标记。
- Agent 最大迭代 10 次防死循环。
- GC 含量保留 2 位小数（`round(gc, 2)`）。
- 所有 git 提交信息以 `Co-Authored-By: Claude Code <noreply@anthropic.com>` 结尾。

## Review Focus

1. sample3 首行缺 `>`、第 2 行含 `X` 和数字 —— 必须**同时**报「缺少 `>` 标题行」和「非法字符」，不能只报第一个。→ Task 2 `test_parse_fasta_reports_all_problems`。
2. `read_log` 日志超过 4000 字符 —— 截断并保留头部、加 `...(truncated)`，不整段丢弃。→ Task 6 `test_read_log_truncates`。
3. `submit_job` 收到未知 `analysis_type` 或不存在的 `filename` —— 拒绝且不创建 job。→ Task 6 `test_submit_job_rejects_bad_input`。
4. `job_status` / `read_log` 收到不存在的 `job_id` —— 返回「不存在」说明，不抛异常、不 500。→ Task 6 `test_tools_unknown_job`。
5. 序列无完整 ORF（或空序列）—— `find_orf` 输出「未找到完整 ORF」且 exit 0（不算失败）。→ Task 3 `test_longest_orf_no_orf`、Task 5 `test_execute_success_empty_output`。
6. 带工具调用的旧会话重放 —— 从 DB 还原出 `role=tool` 消息时带正确 `tool_call_id`，否则模型续聊报错。→ Task 7 `test_reconstructs_tool_messages`。

---

### Task 1: 项目脚手架、样例数据与配置

**Files:**
- Create: `.gitignore`, `.env.example`, `requirements.txt`
- Create: `app/__init__.py`, `app/config.py`, `scripts/__init__.py`
- Create: `data/sample1.fasta`, `data/sample2.fasta`, `data/sample3.fasta`
- Create: `tests/conftest.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `app.config.load_config() -> Settings`（dataclass：`llm_api_key: str`、`llm_base_url: str`、`llm_model: str`、`data_dir: str`、`scripts_dir: str`、`logs_dir: str`、`db_path: str`）。默认值：`llm_base_url="https://api.deepseek.com"`、`llm_model="deepseek-chat"`、`data_dir="data"`、`scripts_dir="scripts"`、`logs_dir="logs/jobs"`、`db_path="app.db"`。用 `python-dotenv` 从 `.env` 读，缺 key 时 `llm_api_key=""`（不报错，让上层决定）。

- [ ] **Step 1: 初始化 git 仓库**

Run: `git init`（在项目根目录 `g:\工作\乐活派\乐活派\claude_code_pro\research_compute`）。

- [ ] **Step 2: 写 `.gitignore`**：排除 `__pycache__/`、`.env`、`app.db`、`logs/`、`.pytest_cache/`、`*.pyc`。`.env.example` 列出 `LLM_API_KEY=`、`LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-chat` 三项（值留空或默认）。

- [ ] **Step 3: 写 `requirements.txt`**：六行 `fastapi`、`uvicorn[standard]`、`openai`、`python-dotenv`、`pytest`、`httpx`。

- [ ] **Step 4: 写三个 `data/*.fasta`**，内容逐字照抄题目三、样例数据（sample1 2 条、sample2 2 条、sample3 首行缺 `>` + 含 `X`/数字）。

- [ ] **Step 5: 写失败测试 `tests/test_config.py`**

```python
def test_defaults_without_env(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    cfg = load_config()
    assert cfg.llm_model == "deepseek-chat"
    assert cfg.llm_base_url == "https://api.deepseek.com"
```

- [ ] **Step 6: 运行测试确认失败** — Run: `pytest tests/test_config.py -v`；Expected: FAIL（`load_config` 未定义）。

- [ ] **Step 7: 实现 `app/config.py`**：`load_config()` 用 `dotenv.load_dotenv()` + `os.environ.get(..., default)` 组装 `Settings`。`tests/conftest.py` 里 `sys.path.insert(0, str(Path(__file__).parent.parent))`。

- [ ] **Step 8: 运行测试确认通过** — `pytest tests/test_config.py -v`；Expected: PASS。

- [ ] **Step 9: 提交**

```bash
git add .gitignore .env.example requirements.txt app scripts data tests
git commit -m "chore: scaffold project, sample data, config"
```

---

### Task 2: 严格 FASTA 解析（scripts/fasta_utils.py）

**Files:**
- Create: `scripts/fasta_utils.py`
- Test: `tests/test_fasta_utils.py`

**Interfaces:**
- Produces: `FastaRecord`（dataclass，字段 `id: str`、`sequence: str`）；`parse_fasta(text: str) -> list[FastaRecord]`。解析失败抛 `ValueError`，消息格式 `"FASTA 解析失败：<问题1>；<问题2>"`，问题形如 `第 N 行缺少以 '>' 开头的标题行`、`第 N 行包含非法字符 X、1、2`（非法字符升序去重）。

**解析规则（唯一非显然逻辑，实现必须照此）**：逐行 strip，跳过空行。维护 `in_record`（是否已开一条记录）。
- 行以 `>` 开头 → 若已有记录先 close；`id = 该行去掉 '>' 后按空白切分的第 1 段`；`sequence = ""`；`in_record = True`。
- 行不以 `>` 开头 → 若 `in_record == False`（即文件第一条内容行就缺 `>`），记一次「第 N 行缺少以 '>' 开头的标题行」，并以该行首个 token 为 id 开一条记录（这样下一行才会被当作序列做字符校验）；否则当作序列行：字符升序去重校验 `A/C/G/T/N`，非法则记「第 N 行包含非法字符 …」，并把大写序列追加到当前记录。
- 结束时关闭最后一条记录。收集到的所有问题合并进一次 `ValueError`（这样 sample3 的两个问题会同时出现在日志里）。

- [ ] **Step 1: 写失败测试 `tests/test_fasta_utils.py`**

```python
def test_parse_two_records():
    recs = parse_fasta(">a desc\nATGC\n>b\nNNNN")
    assert [r.id for r in recs] == ["a", "b"]
    assert recs[0].sequence == "ATGC"

def test_parse_lowercase_and_blank_lines():
    recs = parse_fasta(">a\natgcn\n\n")
    assert recs[0].sequence == "ATGCN"

def test_parse_fasta_reports_all_problems():   # sample3 全文
    text = "seq_bad missing header marker\nATGCCCXXXGGGTTT123AAATAG\n>seq_ok test sequence\nATGAAATTTGGGTAA\n"
    with pytest.raises(ValueError) as e:
        parse_fasta(text)
    msg = str(e.value)
    assert "缺少以 '>' 开头的标题行" in msg
    assert "非法字符" in msg and "X" in msg and "1" in msg
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/test_fasta_utils.py -v`；Expected: FAIL（`parse_fasta` 未定义）。

- [ ] **Step 3: 实现 `parse_fasta` 与 `FastaRecord`**（照上面规则）。

- [ ] **Step 4: 运行确认通过** — Expected: PASS。

- [ ] **Step 5: 提交** — `git add scripts/fasta_utils.py tests/test_fasta_utils.py && git commit -m "feat: strict FASTA parser with multi-problem reporting"`。

---

### Task 3: 分析脚本纯函数 + CLI（scripts/seq_stats.py, scripts/find_orf.py）

**Files:**
- Create: `scripts/seq_stats.py`, `scripts/find_orf.py`
- Test: `tests/test_stats.py`, `tests/test_orf.py`

**Interfaces:**
- Consumes: `scripts.fasta_utils.parse_fasta`, `FastaRecord`。
- Produces:
  - `scripts.seq_stats.stats(records: list[FastaRecord]) -> list[tuple[str, int, float]]`：每项 `(id, 长度, GC% 保留2位)`；空序列长度 0、GC `0.0`。
  - `scripts.seq_stats.main()`：`sys.argv[1]` 读文件，`parse_fasta` 失败则 stderr 打印 `str(e)` 并 `sys.exit(1)`；否则 `time.sleep(random.uniform(3, 5))`，逐行 `print(f"{id}\t{len}\t{gc:.2f}%")`。仅 `if __name__ == "__main__": main()`。
  - `scripts.find_orf.longest_orf(seq: str) -> tuple[int, int, int] | None`：返回 `(起始1-based, 终止1-based含终止子, 长度nt)` 或 `None`。
  - `scripts.find_orf.main()`：同上结构；每条序列 print `f"{id}\t{start}\t{end}\t{length}"`，无 ORF print `f"{id}\t未找到完整ORF"`，exit 0。

**ORF 算法（唯一非显然逻辑，实现必须照此）**：`START="ATG"`、`STOP={"TAA","TAG","TGA"}`。对 `frame in 0..2`：`i=frame`，当 `i+3<=n` 时看 `seq[i:i+3]`；是 `ATG` 就从 `j=i` 起每 3 步找首个 `STOP`，找到则 `orf=(i+1, j+3, j+3-i)`，比较长度取最长，`i=j+3` 继续本读框；找不到 STOP（到末尾）则该读框无完整 ORF、结束本读框。全程维护最长 `best`，最后返回 `best`（无则 `None`）。序列先 `upper()`。

- [ ] **Step 1: 写失败测试**

`tests/test_stats.py`：
```python
def test_stats_gc():
    assert stats([FastaRecord("a", "ATGC")]) == [("a", 4, 50.0)]
    assert stats([FastaRecord("b", "AAAA")]) == [("b", 4, 0.0)]
```

`tests/test_orf.py`：
```python
def test_longest_orf_basic():
    assert longest_orf("ATGAAATAA") == (1, 9, 9)
def test_longest_orf_shifted_frame():
    assert longest_orf("AAATGCCCTAA") == (3, 11, 9)
def test_longest_orf_picks_longest():
    assert longest_orf("ATGTAAATGCCCTAA") == (7, 15, 9)
def test_longest_orf_no_orf():
    assert longest_orf("CCCC") is None
    assert longest_orf("ATG") is None
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/test_stats.py tests/test_orf.py -v`；Expected: FAIL。

- [ ] **Step 3: 实现两个脚本的纯函数与 CLI**（照上面）。

- [ ] **Step 4: 运行确认通过** — Expected: PASS。

- [ ] **Step 5: 提交** — `git add scripts/seq_stats.py scripts/find_orf.py tests/test_stats.py tests/test_orf.py && git commit -m "feat: seq_stats and find_orf analysis scripts"`。

---

### Task 4: SQLite 持久化层（app/db.py）

**Files:**
- Create: `app/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces（全部同步函数，内部 `sqlite3.connect(DB_PATH)`，DB_PATH 为模块级变量默认 `"app.db"`，测试覆盖它）：
  - `init_db() -> None`：建 3 张表（schema 见设计文档 §5.2；`jobs` 表列为 `id TEXT PK, analysis_type TEXT, filename TEXT, status TEXT, exit_code INT, stdout_path TEXT, stderr_path TEXT, created_at TEXT, finished_at TEXT`）。
  - `create_session(title: str) -> int`；`list_sessions() -> list[dict]`（按 `created_at DESC`，键 `id,title,created_at`）；`rename_session(session_id: int, title: str) -> None`。
  - `add_message(session_id: int, role: str, content: str, tool_calls: str | None) -> int`；`list_messages(session_id: int) -> list[dict]`（按 `id ASC`，键含 `id,session_id,role,content,tool_calls,created_at`）。
  - `insert_job(id, analysis_type, filename, status, stdout_path, stderr_path) -> None`；`get_job(id) -> dict | None`；`update_job(id, status=None, exit_code=None, finished_at=None) -> None`（只更新非 None 字段）。

- [ ] **Step 1: 写失败测试 `tests/test_db.py`**（fixture：`db.DB_PATH = str(tmp_path/"t.db")`；`init_db()`）

```python
def test_session_and_message_roundtrip():
    sid = create_session("hello")
    add_message(sid, "user", "hi", None)
    add_message(sid, "assistant", "yo", '[{"id":"c1","name":"job_status","arguments":"{}","result":"ok"}]')
    msgs = list_messages(sid)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["tool_calls"].startswith('[{')

def test_job_roundtrip():
    insert_job("j1", "seq_stats", "sample1.fasta", "running", "a.log", "b.log")
    assert get_job("j1")["status"] == "running"
    update_job("j1", status="success", exit_code=0)
    assert get_job("j1")["status"] == "success"
```

- [ ] **Step 2: 运行确认失败** — Expected: FAIL（`db` 未定义）。

- [ ] **Step 3: 实现 `app/db.py`**。

- [ ] **Step 4: 运行确认通过**。

- [ ] **Step 5: 提交** — `git add app/db.py tests/test_db.py && git commit -m "feat: sqlite persistence for sessions, messages, jobs"`。

---

### Task 5: 后台任务运行器（app/jobs.py）

**Files:**
- Create: `app/jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `app.db.insert_job/get_job/update_job`、`app.config` 的路径常量。
- Produces:
  - `resolve_script(analysis_type: str) -> str`：`{"seq_stats": "scripts/seq_stats.py", "find_orf": "scripts/find_orf.py"}`；未知抛 `ValueError`。
  - `async def execute(job_id: str, cmd: list[str], stdout_path: str, stderr_path: str) -> None`：`asyncio.create_subprocess_exec(*cmd, stdout=open(stdout_path,"wb"), stderr=open(stderr_path,"wb"))`，`await` 结束后按 `returncode==0` 设 `success/failed`、写 `exit_code`、`finished_at`。
  - `async def submit_job(analysis_type: str, filename: str) -> str`：校验 type（`resolve_script`）与 `data/<filename>` 存在（不存在抛 `ValueError`）；`uuid4` 生成 id，`insert_job(status="running")`，`asyncio.create_task(execute(...))` 后台跑，返回 `job_id`。
  - `def get_status(job_id: str) -> str`；`def read_logs(job_id: str, max_chars: int = 4000) -> dict`（键 `stdout,stderr`，各自截断到 `max_chars`，超长加 `...(truncated)`）。

- [ ] **Step 1: 写失败测试 `tests/test_jobs.py`**：用 `tmp_path` 生成两个极短脚本 `ok.py`（print 后 exit 0）与 `fail.py`（stderr 打印后 exit 1），monkeypatch `jobs` 的 logs 目录为 tmp。

```python
def test_execute_success_and_failure(tmp_path):
    # 先写 ok.py / fail.py 到 tmp_path
    await execute("j1", [sys.executable, str(ok)], str(stdout), str(stderr))
    assert get_job("j1")["status"] == "success"
    await execute("j2", [sys.executable, str(fail)], str(stdout2), str(stderr2))
    assert get_job("j2")["status"] == "failed"
    assert get_job("j2")["exit_code"] == 1
```

（`test_jobs.py` 用 `pytest.mark.asyncio` 或 `asyncio.run`；测试自身不含 sleep。）

- [ ] **Step 2: 运行确认失败**。

- [ ] **Step 3: 实现 `app/jobs.py`**。

- [ ] **Step 4: 运行确认通过**。

- [ ] **Step 5: 提交** — `git add app/jobs.py tests/test_jobs.py && git commit -m "feat: async background job runner"`。

---

### Task 6: 三个工具（app/tools.py）

**Files:**
- Create: `app/tools.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Consumes: `app.jobs.submit_job/get_status/read_logs`。
- Produces:
  - `TOOLS: list[dict]`：喂给模型的 function 定义，名 `submit_job`/`job_status`/`read_log`，参数与下面签名一致。
  - `async def submit_job(analysis_type: str, filename: str) -> str`：返回 `"任务已提交，job_id=<id>（任务约几秒完成，请调用 job_status 轮询状态）"`。
  - `async def job_status(job_id: str) -> str`：未知 id 返回 `"未找到该任务"`；否则返回 `"状态：<status>"`。
  - `async def read_log(job_id: str) -> str`：未知 id 返回 `"未找到该任务"`；否则返回 `"stdout:\n<...>\nstderr:\n<...>"`（走 `read_logs` 截断）。
  - `TOOL_HANDLERS: dict[str, callable]`：名字 → 上述 async 函数，供 agent 分发。

- [ ] **Step 1: 写失败测试 `tests/test_tools.py`**（monkeypatch jobs 的 data/logs 目录到 tmp；预置 `data/sample1.fasta` 和一段长日志）

```python
def test_submit_job_rejects_bad_input():
    with pytest.raises(ValueError):
        asyncio.run(submit_job("nope", "sample1.fasta"))
    with pytest.raises(ValueError):
        asyncio.run(submit_job("seq_stats", "missing.fasta"))

def test_tools_unknown_job():
    assert asyncio.run(job_status("nope")) == "未找到该任务"
    assert asyncio.run(read_log("nope")) == "未找到该任务"

def test_read_log_truncates():
    # 造一个 > 4000 字符的日志文件，调用 read_log 断言包含 "...(truncated)" 且长度受限
```

- [ ] **Step 2: 运行确认失败**。

- [ ] **Step 3: 实现 `app/tools.py`**（含 `TOOLS` 的 JSON schema 与 `TOOL_HANDLERS`）。

- [ ] **Step 4: 运行确认通过**。

- [ ] **Step 5: 提交** — `git add app/tools.py tests/test_tools.py && git commit -m "feat: submit_job/job_status/read_log tools"`。

---

### Task 7: LLM 客户端 + Agent 循环（app/llm.py, app/agent.py）

**Files:**
- Create: `app/llm.py`, `app/agent.py`
- Test: `tests/test_agent.py`

**Interfaces:**
- Consumes: `app.tools.TOOLS/TOOL_HANDLERS`、`app.db.list_messages/add_message`。
- Produces:
  - `app.llm.LLMClient(api_key, base_url, model)`：`async def stream_chat(messages: list[dict], tools: list[dict])`，异步迭代 yield `dict`，每项 `{"content": str|None, "tool_calls": list[dict]|None}`（tool_call dict 键 `id,name,arguments`，arguments 为 JSON 字符串）。内部用 `AsyncOpenAI`，流式累积 delta（content delta 与 tool_calls delta；tool_calls 按 index 累积 `id/function.name/function.arguments`）。若流式结束出现 tool_calls 但 delta 未拼出，则用一次非流式补拉。
  - `app.agent.SYSTEM_PROMPT: str`：必须含「submit_job 后要反复 job_status 直到 success/failed」「status 为 failed 先 read_log 再通俗解释 + 给建议」「汇报结果讲清条数/长度/GC」。
  - `async def run_agent(session_id: int, user_text: str, llm, send) -> None`：`send` 为 `async def send(event: str, data: dict|str) -> None`。
    - 流程：从 DB 读历史（含新 user 消息），构造 OpenAI messages（把 assistant 工具行还原成 `role=assistant`(tool_calls) + 若干 `role=tool`(带 `tool_call_id`)）；循环最多 10 次 `stream_chat`；工具轮执行工具、逐工具 `await send("tool_call", {...})` / `await send("tool_result", {...})`，追加 `role=tool` 消息；文本轮逐 delta `await send("token", {"delta": d})`；结束后把最终 assistant 文本与工具调用（含 result）落库，`await send("done", {})`；异常 `await send("error", {"message": ...})`。

- [ ] **Step 1: 写失败测试 `tests/test_agent.py`**：`FakeLLM` 实现 `stream_chat`，按脚本依次 yield —— 成功路径：`{tool_calls:[submit_job]}` → `{tool_calls:[job_status]}` → `{tool_calls:[job_status]}` → `{tool_calls:[read_log]}` → `{content:"共 2 条序列…"}`；失败路径：submit → job_status(failed) → read_log → 解释文本。用真实 tools（jobs 用 tmp 目录 + 真实 seq_stats 短脚本）或 monkeypatch `TOOL_HANDLERS` 成固定返回。断言：

```python
async def test_agent_success_path_emits_tool_and_token(events):
    await run_agent(sid, "统计 sample1 GC", FakeLLM(成功脚本), collect(events))
    names = [e for e in events if e[0] == "tool_call"]
    assert [n[1]["name"] for n in names] == ["submit_job", "job_status", "job_status", "read_log"]
    assert any(e[0] == "token" for e in events)

def test_reconstructs_tool_messages():  # 见 Review Focus 6
    # list_messages 含一条 tool_calls JSON 行，断言构造出的 messages 里
    # 存在 role=="tool" 且 tool_call_id==对应 id 且 content==result
```

- [ ] **Step 2: 运行确认失败**。

- [ ] **Step 3: 实现 `app/llm.py` 与 `app/agent.py`**。

- [ ] **Step 4: 运行确认通过**。

- [ ] **Step 5: 提交** — `git add app/llm.py app/agent.py tests/test_agent.py && git commit -m "feat: agent loop with streaming tool calls"`。

---

### Task 8: FastAPI 后端 + SSE（app/main.py）

**Files:**
- Create: `app/main.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `run_agent`、`db.*`、`config.load_config`。
- Produces:
  - `GET /api/sessions` → `{"sessions": [...]}`；`POST /api/sessions`（body `{"title"}`）→ `{"id": ...}`；`GET /api/sessions/{id}/messages` → `{"messages": [...]}`。
  - `POST /api/chat`（body `{"session_id", "message"}`）→ `StreamingResponse`（`text/event-stream`）。SSE 帧格式 `event: <name>\ndata: <json>\n\n`。先把 user 消息落库，再用异步生成器桥接 `run_agent` 的 `send` 回调为 SSE。
  - `GET /` 与 `/static` 托管 `static/`。
  - 启动时 `init_db()`。

- [ ] **Step 1: 写失败测试 `tests/test_api.py`**：`TestClient(app)`；注入 fake LLM（monkeypatch 一个全局 `app.main.llm_factory` 返回 FakeLLM）。断言 `POST /api/sessions` 后 `GET /api/sessions` 含新会话；`POST /api/chat` 响应体包含 `event: token` 与 `event: tool_call`；刷新语义（再次 `GET messages`）能拿到落库消息。

- [ ] **Step 2: 运行确认失败**。

- [ ] **Step 3: 实现 `app/main.py`**。

- [ ] **Step 4: 运行确认通过**。

- [ ] **Step 5: 提交** — `git add app/main.py tests/test_api.py && git commit -m "feat: fastapi app with SSE chat endpoint"`。

---

### Task 9: 前端（static/index.html, app.js, style.css）

**Files:**
- Create: `static/index.html`, `static/app.js`, `static/style.css`

**Interfaces:**
- Consumes: `GET/POST /api/sessions`、`GET /api/sessions/{id}/messages`、`POST /api/chat`（SSE）。
- Produces（行为，非测试接口）：
  - 左栏会话列表 + 「新建会话」按钮；点击切换并加载历史。
  - 主区消息流：用户右、助手左；助手消息里工具卡片（name/args/result）可折叠。
  - 输入框回车发送：`fetch POST /api/chat`，读 `response.body` 流，按 `\n\n` 切帧、逐行解析 `event:`/`data:`，`token` 逐字追加、`tool_call`/`tool_result` 建/更新卡片、`done` 恢复输入。
  - SSE 解析器必须正确处理跨 chunk 边界（一个 data 行被拆到多次 read）。

- [ ] **Step 1: 写 `index.html`（骨架）、`style.css`（左右气泡、可折叠卡片、左栏）、`app.js`（会话管理 + SSE 解析 + 渲染）**。

- [ ] **Step 2: 用浏览器验证**（先启动 uvicorn，再用 browser-automation 技能）——检查：会话列表可新建/切换；发送消息能看到逐字流式与工具卡片折叠；刷新后历史仍在。若发现 console 报错或未渲染，修复后重验。

- [ ] **Step 3: 提交** — `git add static && git commit -m "feat: vanilla JS chat frontend with SSE streaming"`。

---

### Task 10: README、收尾与端到端验证

**Files:**
- Create: `README.md`

- [ ] **Step 1: 写 `README.md`**：安装（`pip install -r requirements.txt`）、配置（复制 `.env.example` 为 `.env` 填 `LLM_API_KEY`）、启动（`uvicorn app.main:app --reload` 或 `python -m uvicorn`）、架构说明（一段文字 + 目录树）、取舍（无 Docker/无 MCP/无文件上传，说明理由）、未完成项。

- [ ] **Step 2: 全量测试** — Run: `pytest -q`；Expected: 全绿。

- [ ] **Step 3: 真实端到端验证**（用户已确认提供 DeepSeek key，key 在 `.env`）——启动服务，用浏览器对 sample1 做 seq_stats（成功路径）与 sample3（失败→读日志→解释），确认符合预期；不符则用 systematic-debugging 修。

- [ ] **Step 4: 提交** — `git add README.md && git commit -m "docs: README with setup, architecture, tradeoffs"`。

- [ ] **Step 5: 检查提交历史** — Run: `git log --oneline`；确认每个任务至少一个提交、无 `.env`/`app.db` 被跟踪。

---
