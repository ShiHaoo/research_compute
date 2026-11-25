"""Agent 循环：模型思考 → 调用工具 → 拿到结果 → 继续思考，直到给出最终回答。"""
import json

from app import db
from app.tools import TOOL_HANDLERS, TOOLS

MAX_ITERATIONS = 10

SYSTEM_PROMPT = (
    "你是「科研计算任务助手」。你可以用以下工具帮用户在本机运行序列分析任务：\n"
    "- submit_job(analysis_type, filename)：提交任务（analysis_type 是 seq_stats 或 find_orf；"
    "filename 是 data/ 目录下的 FASTA 文件，如 sample1.fasta）。\n"
    "- job_status(job_id)：查询任务状态（running / success / failed）。\n"
    "- read_log(job_id)：读取任务的 stdout / stderr 日志。\n\n"
    "规则：\n"
    "1. submit_job 的任务在后台异步运行，大约要几秒。提交后你必须反复调用 job_status 轮询，"
    "直到状态变成 success 或 failed，绝不要只查一次就下结论。\n"
    "2. 当 job_status 返回 failed 时，你必须先调用 read_log 查看日志，然后用普通人能听懂的话"
    "解释失败原因，并给出修改建议。\n"
    "3. 任务成功后，把结果讲清楚：seq_stats 要说明有多少条序列、各自的长度和 GC 含量；"
    "find_orf 要说明每条序列最长 ORF 的起止位置和长度。\n"
    "4. 用中文简洁、准确地回答。"
)


def build_messages(session_id: int) -> list[dict]:
    """从 DB 还原 OpenAI 格式的消息序列（含把 assistant 工具行拆成 role=tool 消息）。"""
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for row in db.list_messages(session_id):
        role = row["role"]
        if role == "user":
            messages.append({"role": "user", "content": row["content"]})
        elif role == "assistant":
            if row["tool_calls"]:
                tool_calls = json.loads(row["tool_calls"])
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                            },
                        }
                        for tc in tool_calls
                    ],
                })
                for tc in tool_calls:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tc["result"],
                    })
            else:
                messages.append({"role": "assistant", "content": row["content"]})
    return messages


async def _dispatch(name: str, args: dict) -> str:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return f"未知工具: {name}"
    try:
        return await handler(**args)
    except Exception as e:  # noqa: BLE001 - 工具出错要转成可读文本喂回模型
        return f"工具执行出错: {e}"


async def run_agent(session_id: int, llm, send) -> None:
    """跑一轮 Agent 循环。``send`` 是 ``async def send(event, data)`` 回调。"""
    try:
        messages = build_messages(session_id)
        for _ in range(MAX_ITERATIONS):
            turn_text: list[str] = []
            turn_tool_calls: list[dict] = []
            async for item in llm.stream_chat(messages, TOOLS):
                if item["kind"] == "delta":
                    turn_text.append(item["content"])
                    await send("token", {"delta": item["content"]})
                elif item["kind"] == "tool_calls":
                    raw_calls = item["tool_calls"]
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": tc["arguments"] or "{}",
                                },
                            }
                            for tc in raw_calls
                        ],
                    })
                    for tc in raw_calls:
                        args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                        await send("tool_call", {"name": tc["name"], "arguments": args})
                        result = await _dispatch(tc["name"], args)
                        await send("tool_result", {"name": tc["name"], "result": result})
                        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                        turn_tool_calls.append({
                            "id": tc["id"],
                            "name": tc["name"],
                            "arguments": args,
                            "result": result,
                        })

            if turn_tool_calls:
                if turn_text:
                    db.add_message(session_id, "assistant", "".join(turn_text), None)
                db.add_message(session_id, "assistant", "", json.dumps(turn_tool_calls, ensure_ascii=False))
                continue

            final_text = "".join(turn_text)
            if final_text:
                db.add_message(session_id, "assistant", final_text, None)
            break
        else:
            notice = "已达到最大迭代次数（10 次），仍未得到最终回答，请稍后重试。"
            await send("token", {"delta": notice})
            db.add_message(session_id, "assistant", notice, None)

        await send("done", {})
    except Exception as e:  # noqa: BLE001 - 任何异常都要回给前端
        await send("error", {"message": str(e)})
