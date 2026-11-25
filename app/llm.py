"""DeepSeek（OpenAI 兼容）流式客户端。

``stream_chat`` 是异步迭代器，产出归一化事件：
- ``{"kind": "delta", "content": str}``            —— 最终答案的逐字增量
- ``{"kind": "tool_calls", "tool_calls": [...]}``  —— 一次工具调用轮（一次一条）
"""
from openai import AsyncOpenAI


class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.model = model
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def stream_chat(self, messages: list[dict], tools: list[dict]):
        stream = await self.client.chat.completions.create(
            messages=messages,
            model=self.model,
            tools=tools or None,
            stream=True,
        )

        tool_calls: dict[int, dict] = {}
        finish_reason = None

        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            finish_reason = choice.finish_reason
            delta = choice.delta
            if delta is None:
                continue
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    slot = tool_calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    fn = tc.function
                    if fn is not None:
                        if fn.name:
                            slot["name"] = fn.name
                        if fn.arguments:
                            slot["arguments"] += fn.arguments
            elif delta.content:
                yield {"kind": "delta", "content": delta.content}

        if tool_calls:
            yield {"kind": "tool_calls", "tool_calls": [tool_calls[i] for i in sorted(tool_calls)]}
        elif finish_reason == "tool_calls":
            # 流式未给出 tool_calls delta 时，用一次非流式兜底
            resp = await self.client.chat.completions.create(
                messages=messages,
                model=self.model,
                tools=tools or None,
            )
            calls = []
            for c in (resp.choices[0].message.tool_calls or []):
                calls.append({
                    "id": c.id,
                    "name": c.function.name,
                    "arguments": c.function.arguments or "{}",
                })
            yield {"kind": "tool_calls", "tool_calls": calls}
