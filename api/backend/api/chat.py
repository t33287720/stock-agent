"""API 區：問股票聊天。"""
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import iterate_in_threadpool

from backend.control.llm.chat import chat_stream

router = APIRouter()


class ChatBody(BaseModel):
    history: list[dict] = []
    message: str


@router.post("/api/chat")
async def chat(body: ChatBody):
    """以 NDJSON 串流回傳聊天問答過程：先解析股票、抓資料/搜尋，最後給出回覆。"""
    async def event_stream():
        gen = chat_stream(body.history, body.message)
        async for event in iterate_in_threadpool(gen):
            yield json.dumps(event, ensure_ascii=False) + "\n"
    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
