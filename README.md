# 科研计算任务助手（Research Compute Assistant）

一个带前后端的智能体应用：研究员用自然语言和它对话，它自动调用工具，在本机异步运行
序列分析任务、查询状态、读取日志并解释结果。

## 功能

- **聊天界面**：回复逐字流式显示；每次调用工具都能看到「调了哪个工具、传了什么参数、
  返回了什么」，可折叠；左侧历史会话列表，可新建 / 切换。
- **Agent 循环**：自己实现「模型思考 → 调用工具 → 拿到结果 → 继续思考」，直到给出最终回答。
- **持久化**：会话与消息存 SQLite，刷新页面、重启后端历史不丢。
- **三个工具**：`submit_job`（异步提交任务）、`job_status`（查状态）、`read_log`（读日志，过长截断）。
- **两个分析脚本**：`seq_stats`（每条序列 ID / 长度 / GC 含量）、`find_orf`（正链最长 ORF 起止位置与长度）。
- **失败处理**：任务失败时智能体主动读日志，用大白话解释原因并给建议。

## 技术栈

- 后端：Python 3.12 + FastAPI + uvicorn + openai SDK（指向 DeepSeek，OpenAI 兼容）
- 数据库：SQLite（Python 标准库 `sqlite3`，无 ORM）
- 前端：原生 HTML / CSS / JavaScript（无构建步骤，由 FastAPI 直接托管）
- 分析脚本：纯 Python（不依赖 Biopython），由后端以子进程启动

## 目录结构

```
research_compute/
├── app/
│   ├── main.py        # FastAPI 路由 + 静态托管 + SSE 聊天接口
│   ├── config.py      # 读 .env 配置
│   ├── db.py          # SQLite 持久化（sessions / messages / jobs）
│   ├── llm.py         # DeepSeek 流式客户端（OpenAI 兼容）
│   ├── agent.py       # Agent 循环（思考→调工具→继续思考）
│   ├── tools.py       # submit_job / job_status / read_log
│   └── jobs.py        # 后台子进程任务运行器
├── scripts/
│   ├── fasta_utils.py # 严格 FASTA 解析与校验
│   ├── seq_stats.py   # 序列统计（长度 / GC 含量）
│   └── find_orf.py    # 最长开放阅读框
├── data/              # sample1/2/3.fasta（sample3 故意有格式错误）
├── static/            # index.html / app.js / style.css
├── tests/             # pytest 单元测试
└── README.md
```

## 安装与启动

### 1. 准备环境

需要 Python 3.10+（开发用 3.12）。在项目根目录：

```bash
# 创建并激活虚拟环境
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置大模型 API Key

复制 `.env.example` 为 `.env`，填入你的 DeepSeek API Key（`.env` 已被 gitignore，不会提交）：

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

编辑 `.env`：

```
LLM_API_KEY=sk-你的密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

换用其它 OpenAI 兼容模型（通义千问、智谱等）只需改 `LLM_BASE_URL` 和 `LLM_MODEL`。

### 3. 启动后端

在项目根目录：

```bash
uvicorn app.main:app --reload
```

打开浏览器访问 <http://127.0.0.1:8000>。

### 4. 试一下

- 输入「帮我统计 sample1 里序列的 GC 含量」→ 会看到 `submit_job` 提交、`job_status` 轮询、
  `read_log` 读日志，最终逐字输出结果。
- 输入「对 sample3 做一次 find_orf」→ 任务失败，智能体会读日志并解释：文件缺少以 `>` 开头的
  标题行、序列中有非法字符，并给出修改建议。

## 架构说明

```
浏览器（原生 JS 单页）
   │  REST + SSE（text/event-stream）
   ▼
FastAPI（app/main.py）
   │
   ├─ app/agent.py  ── Agent 循环：每轮流式调模型，
   │       │            返回 tool_calls 就执行工具、把结果回填继续思考，
   │       │            返回文本就逐字推给前端
   │       ├─ app/llm.py   ── DeepSeek（OpenAI 兼容）流式客户端
   │       └─ app/tools.py ── submit_job / job_status / read_log
   │
   ├─ app/jobs.py   ── 后台任务：asyncio.create_subprocess_exec
   │       │             启动 scripts/*.py，stdout/stderr 落盘，状态写库
   │       └─ scripts/seq_stats.py / find_orf.py
   │
   └─ app/db.py     ── SQLite：sessions / messages / jobs
```

**SSE 事件**：后端用 `text/event-stream` 推送五类事件——`token`（最终答案逐字增量）、
`tool_call`（工具名 + 参数）、`tool_result`（工具返回）、`done`、`error`。前端据此渲染
流式文本与可折叠工具卡片。

**任务执行**：`submit_job` 先写一条 `status=running` 的 job 记录，再用
`asyncio.create_task` 启动子进程，**不阻塞对话**；脚本退出后按返回码把状态更新为
`success` / `failed`，stdout/stderr 落到 `logs/jobs/<id>.*.log`。

**失败处理**：系统提示词约束模型——`job_status` 返回 `failed` 时必须先 `read_log`，
再用通俗语言解释原因并给建议（而不是只回一句「任务失败了」）。sample3 的 FASTA 校验器
会一次报告全部问题（缺 `>` 标题行 + 非法字符）。

## 两个分析任务

| 脚本 | 输出 | 说明 |
|---|---|---|
| `seq_stats.py` | 每条 `ID 长度 GC%` | GC 含量保留 2 位小数 |
| `find_orf.py` | 每条 `ID 起始 终止 长度` | 正链三读框中最长完整 ORF（`ATG` 起、`TAA/TAG/TGA` 止，位置 1-based） |

每个脚本内部有 3–5 秒延时，模拟真实计算耗时。脚本可独立运行：
`python -m scripts.seq_stats data/sample1.fasta`。

## 测试

```bash
pytest -q
```

覆盖 FASTA 校验、ORF 算法、DB 读写、任务运行器、三个工具、Agent 循环（用 mock LLM，无需真实 key）、
API 接口。

## 取舍与未完成项

**做的取舍**

- **原生 JS 前端而非 React**：题目强调「不追求功能多，更看重扎实、理解代码」，单页无构建更稳、
  更好当面讲清。
- **openai SDK + 手写循环而非 LangChain 等框架**：考题要求「自己实现这个循环」，只允许模型厂商 SDK。
- **纯模型驱动，不写死路径**：是否轮询、是否读日志由模型根据提示词自主决定，符合「思考→调工具」的定位。
- **sqlite3 标准库而非 ORM**：三张表、几组查询，标准库足够且可解释。

**没来得及做（加分项）**

- Docker Compose 一键启动（本机未装 Docker）。
- 用 MCP 协议封装三个工具。
- 界面上传自己的 FASTA 文件。
- 任务完成后主动推送通知（当前前端已实时展示过程，但需用户发起）。

## 关于演示录屏

建议录屏展示：新建会话 → 对 sample1 做 seq_stats（成功路径：提交 / 轮询 / 读日志 / 结果）→
对 sample3 做任意分析（失败路径：读日志 + 通俗解释 + 建议）→ 刷新页面验证历史不丢。
