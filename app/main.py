"""FastAPI 应用：托管静态前端 + 会话/消息/聊天(SSE)接口。"""
import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# 允许直接 `python app/main.py` 运行：此时脚本目录 app/ 是 sys.path[0]，
# 把项目根也加进去，`from app import ...` 才能解析
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import db
from app.agent import run_agent
from app.config import load_config
from app.llm import LLMClient

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def get_llm() -> LLMClient:
    cfg = load_config()
    return LLMClient(cfg.llm_api_key, cfg.llm_base_url, cfg.llm_model)


class CreateSessionRequest(BaseModel):
    title: str = "新会话"


class ChatRequest(BaseModel):
    session_id: int
    message: str


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/sessions")
def list_sessions():
    return {"sessions": db.list_sessions()}


@app.post("/api/sessions")
def create_session(req: CreateSessionRequest):
    sid = db.create_session(req.title)
    return {"id": sid}


@app.get("/api/sessions/{session_id}/messages")
def get_messages(session_id: int):
    out = []
    for m in db.list_messages(session_id):
        tc = m["tool_calls"]
        out.append({
            "id": m["id"],
            "session_id": m["session_id"],
            "role": m["role"],
            "content": m["content"],
            "tool_calls": json.loads(tc) if tc else None,
            "created_at": m["created_at"],
        })
    return {"messages": out}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not any(s["id"] == req.session_id for s in db.list_sessions()):
        raise HTTPException(status_code=404, detail="会话不存在")

    db.add_message(req.session_id, "user", req.message, None)
    if len(db.list_messages(req.session_id)) == 1:
        db.rename_session(req.session_id, req.message[:20])

    llm = get_llm()

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()

        async def send(event, data):
            await queue.put(("event", event, data))

        async def runner():
            try:
                await run_agent(req.session_id, llm, send)
            finally:
                await queue.put(("stop", None, None))

        task = asyncio.create_task(runner())
        while True:
            kind, event, data = await queue.get()
            if kind == "stop":
                break
            yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        await task

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
