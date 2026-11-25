# 设计文档：科研计算任务助手（Research Compute Assistant）

日期：2026-11-25
状态：待确认

## 1. 意图与为什么（Intent & Why）

这是一道智能体开发实践考题：研究员用自然语言和一个带工具的智能体对话，智能体在本机调用
工具，异步运行序列分析任务、查询状态、读日志并解释结果。我要交付的是一个**能跑、扎实、
我本人能讲清每一行**的全栈应用，而不是功能堆砌。

目标读者/使用场景：考官会在自己的电脑上按 README 一步步跑起来，然后约 1 小时面谈，让我讲
设计并当场做一个改动。所以代码要**简单、可解释、可现场修改**。

## 2. 目标 / 非目标 / 反目标

### 目标（必须做）
1. 前端聊天界面：用户提问 → 回复逐字流式输出；每次调用工具时能看到「调了哪个工具、传了什么
   参数、返回了什么」，可折叠；左侧历史会话列表，可新建/切换。
2. 后端智能体：接 DeepSeek，**自己实现**「模型思考 → 调用工具 → 拿到结果 → 继续思考」的循环，
   直到给出最终回答；不用 Dify/Coze 之类低代码平台。
3. 会话与消息存 SQLite，刷新页面、重启后端历史不丢。
4. 三个工具：`submit_job`（异步提交任务，返回任务 ID）、`job_status`（查状态：运行中/成功/失败）、
   `read_log`（读 stdout/stderr 日志，太长截断）。
5. 两个分析脚本，以独立子进程由后端启动：`seq_stats`（每条序列 ID/长度/GC 含量）、
   `find_orf`（正链最长 ORF，起止位置+长度），脚本内加 3–5 秒延时。
6. 失败处理：任务失败时，智能体**主动读日志**，用普通人能懂的话解释原因并给建议（不是只回一句
   "任务失败了"）。
7. 样例数据放在 `data/`，其中 sample3 格式有问题，系统要能正确处理（检测并友好报告失败）。
8. README 说明安装/启动/架构/取舍/未完成项；API Key 放配置文件或环境变量，不进 git。
9. 保留 git 提交历史。

### 非目标（这版不做，写进 README）
- 多机部署 / 集群 / 认证鉴权。
- 复杂的向量检索、RAG、多 Agent 编排。

### 反目标（做了就算失败）
- 用 Dify/Coze 等低代码平台套壳。
- 让提交任务阻塞对话（必须后台异步）。
- 失败只回一句"任务失败了"而不解释。
- 把 API Key 提交进仓库。

## 3. 约束

- 本机 Windows 10（已装 Python 3.12.9 + Node 24），**无 Docker**（Docker Compose 加分项先不做，
  README 里注明）。
- 大模型用 DeepSeek（OpenAI 兼容接口），API Key 放 `.env`，不提交。
- 分析脚本统一 Python；前后端技术栈已选定：后端 FastAPI + 原生 JS 单页前端（无前端构建步骤）。

## 4. 方案对比（Approaches）

| 方案 | 说明 | 取舍 |
|---|---|---|
| A. FastAPI + 原生 JS 前端（**已选**） | 后端 FastAPI 跑 Agent 循环 + 子进程；前端一个 HTML+JS 单页由 FastAPI 托管，SSE 流式 | 代码最少、无前端构建链、最稳、最好当面讲清；UI 扩展性一般 |
| B. FastAPI + React(Vite) | 前端 React+TS 独立构建 | UI 更规范，但多一套 node 构建与依赖，3 天内调试成本高 |
| C. Node 全栈 | Express + React 统一 TS | 分析脚本仍是 Python，等于维护两门语言，Agent 循环更绕 |

选 A 的理由：题目明说"不追求功能多，更看重扎实、理解自己的代码"，且面谈要当场改动，
单语言后端 + 无构建前端最符合这个定位。

## 5. 已决定的实现细节

### 5.1 目录结构
```
research_compute/
├── README.md
├── .env.example            # 提交；.env 不提交
├── .gitignore
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI 路由 + 静态托管
│   ├── config.py           # 读 .env（LLM key/base_url/model）
│   ├── db.py               # SQLite（sqlite3 标准库）
│   ├── llm.py              # DeepSeek/OpenAI 兼容客户端
│   ├── agent.py            # Agent 循环 + SSE 流式
│   ├── tools.py            # submit_job / job_status / read_log
│   └── jobs.py             # 后台子进程任务运行器
├── scripts/
│   ├── fasta_utils.py      # 共享 FASTA 解析 + 严格校验
│   ├── seq_stats.py
│   └── find_orf.py
├── data/                   # sample1/2/3.fasta
├── static/                 # index.html / app.js / style.css
├── tests/                  # 单元测试
└── logs/jobs/              # 运行时日志，gitignore
```

### 5.2 数据模型（SQLite，sqlite3 标准库，无 ORM）
```sql
sessions(id INTEGER PK AUTOINCREMENT, title TEXT, created_at TEXT)
messages(id INTEGER PK, session_id INTEGER REFERENCES sessions, role TEXT,
         content TEXT, tool_calls TEXT /*JSON*/, created_at TEXT)
jobs(id TEXT PK /*uuid*/, analysis_type TEXT, filename TEXT, status TEXT,
     exit_code INTEGER, stdout_path TEXT, stderr_path TEXT,
     created_at TEXT, finished_at TEXT)
```
- `messages.tool_calls`（仅 assistant 工具调用轮使用）存 JSON 数组，每个元素
  `{id, name, arguments, result}`；`result` 为该工具的返回结果，**就地存**。前端据此渲染
  "工具名 + 参数 + 结果"卡片，刷新/重启后原样读回。
- 重放给模型时，由一条 assistant 工具行还原出 `role=assistant`（tool_calls，去掉 result）加若干
  `role=tool`（带 `tool_call_id` + `content`）消息，保证带工具的历史会话能被模型正确续聊。
- 会话标题取用户第一条消息前 ~20 字。

### 5.3 工具定义（喂给模型的 JSON Schema 与实现一致）
- `submit_job(analysis_type, filename)`：校验 type ∈ {seq_stats, find_orf}、filename 存在于
  `data/`；写 jobs 行 status=running；用 `asyncio.create_subprocess_exec` 异步启动
  `python scripts/<type>.py data/<filename>`，stdout/stderr 重定向到日志文件；完成时按 exit code
  更新 status=success/failed。**不阻塞对话**。返回 job_id。
- `job_status(job_id)`：查 jobs 行，返回 {status, analysis_type, filename, created_at, finished_at}。
- `read_log(job_id)`：读 stdout+stderr 文件，各截断到 ~4000 字符，超出加 `...(truncated)` 标记。

### 5.4 Agent 循环（agent.py）
系统提示词要点：你是科研计算助手，可用工具提交/查询任务、读日志；**submit_job 提交的任务要几秒，
你必须反复调用 job_status 直到变成 success 或 failed，不许只查一次就停下**；**当 job_status 返回
failed 时，必须先 read_log，用通俗语言解释失败原因并给出建议**；报告结果时把数据讲清楚（条数/长度/GC 等）。

循环（纯模型驱动，不写代码强制的固定路径；最大迭代 10 次防死循环）：
1. 组装 messages（历史 + 新用户消息）+ tools。
2. 流式调用模型，边收 delta 边分流：
   - 出现 tool_calls delta → 本轮是工具轮，累积各工具的 id/name/arguments（不向前端发文本）；
   - 出现 content delta 且非工具轮 → 发 SSE `token` 事件（最终答案的逐字流式）。
3. 工具轮结束后：逐个执行工具，发 `tool_call` / `tool_result` 事件，把 `role=tool`（带 tool_call_id）
   消息追加进 messages，回到步骤 2。
4. 文本轮结束后：落库 assistant 文本 + 工具调用（含 result），发 `done`。
注：llm.py 对 DeepSeek 的流式 tool_calls 做 delta 累积，并留非流式兜底（若流式不返回 tool_calls 则
用一次非流式重试），不赌 API 具体行为。

SSE 事件类型：`token`（文本增量）、`tool_call`（{name, args}）、`tool_result`（{name, result}）、
`done`、`error`。前端据此分别渲染逐字文本与可折叠工具卡片。

### 5.5 分析脚本（纯 Python + 共享 fasta_utils，不依赖 Biopython）
- `fasta_utils.py`：严格 FASTA 解析。规则：
  - 每行去掉空白；空行跳过。
  - 以 `>` 开头 → 新 header；否则视为序列行，但若当前还没有 header（即文件第一行不是 `>`）→ 报错
    `第 N 行缺少以 '>' 开头的标题行`。
  - 序列字符必须是 `ACGTN`（大小写均可）；出现 `X`、数字等 → 报错 `第 N 行包含非法字符 '...'`。
  - 这正好让 sample3 失败：第 1 行无 `>`、第 2 行含 `X` 和数字。
- `seq_stats.py <fasta>`：逐条输出 `ID\t长度\tGC含量%`（TSV），sleep 3–5s，异常时 stderr 写中文错误、exit 1。
- `find_orf.py <fasta>`：每条序列在三个读框内扫描，遇 `ATG` 起始、找同读框内第一个终止密码子
  `TAA/TAG/TGA`，取最长 ORF；输出 `ID\t起始(1-based)\t终止(1-based，含终止子)\t长度(nt)`，sleep 3–5s。
- 脚本只在收到合法命令行参数、读文件时才 sleep；导入本模块时（供测试）不自动 sleep。

### 5.6 前端（static/，原生 JS）
- 左侧会话列表（GET /api/sessions，新建 POST /api/sessions，点击切换 GET messages）。
- 主区消息流；用户消息与助手消息分左右。
- 助手回复里嵌工具卡片（可点击折叠/展开，显示 name/args/result）。
- 输入框回车发送：`fetch POST /api/chat`（body 为 session_id+message），读 `response.body` 流，
  按 `event:` / `data:` 手动解析 SSE，逐 delta 追加文本。
- 发送中禁用输入，`done` 后恢复。

### 5.7 配置与安全
- `config.py` 用 `python-dotenv` 读 `.env`：`LLM_API_KEY`、`LLM_BASE_URL`（默认
  `https://api.deepseek.com`）、`LLM_MODEL`（默认 `deepseek-chat`）。
- `.env` 进 `.gitignore`；`.env.example` 提交模板。LLM 客户端用 `openai` SDK 指向 DeepSeek base_url。

### 5.8 测试（tests/，pytest）
- `test_fasta.py`：合法 FASTA 解析、缺 `>` 报错、非法字符报错、sample3 触发失败。
- `test_tools.py`：submit_job 参数校验、job_status、read_log 截断。
- `test_orf.py`：已知序列的最长 ORF 起止/长度断言。
- `test_jobs.py`：子进程成功/失败路径的状态流转（用短脚本、绕过 sleep）。
- `test_agent.py`：用 mock LLM 桩（返回脚本化的 tool_calls/文本）测 Agent 循环，覆盖
  "submit → poll → read_log → final" 成功路径与 "failed → read_log" 失败路径，无需真实 key。

## 6. 留给构建者的余地

- 具体错误文案、日志截断长度（默认 4000）、最大迭代次数（10）、GC 保留位数（2 位）等细节由构建者定。
- 前端样式（配色/布局）由构建者自定，但要干净可用。
- 加分项（MCP、主动通知、上传文件、Docker）这版不做，README 里说明取舍。

## 7. 验收口径

- README 步骤能在一台空 Windows/Python 机器上跑通；配好 `.env` 后，与助手对话能：提交 sample1
  的 seq_stats → 等到 success → 读日志 → 汇报结果；对 sample3 能：失败 → 主动读日志 → 用大白话解释
  缺 `>` 与非法字符 → 给建议。
- 前端能看到流式逐字输出与可折叠工具卡片；刷新/重启后会话与消息还在。
