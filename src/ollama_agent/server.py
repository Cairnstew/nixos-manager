"""
FastAPI server exposing ollama_agent as an OpenAI-compatible chat completions API.

Any tool that supports a custom OpenAI base URL will work:
  - Continue:   set api_base to http://localhost:8000/v1
  - Aider:      aider --openai-api-base http://localhost:8000/v1 --model agent
  - OpenCode:   set baseURL to http://localhost:8000/v1
  - curl:       curl http://localhost:8000/v1/chat/completions ...
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ollama_agent.agents.factory import create_agent
from ollama_agent.config import AgentType, OllamaConfig

logger = logging.getLogger(__name__)

app = FastAPI(
    title="ollama-agent",
    description="OpenAI-compatible API backed by a local Ollama agent.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------- #
# OpenAI-compatible request / response schemas                                #
# --------------------------------------------------------------------------- #

class ChatMessage(BaseModel):
    role: str
    content: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = "agent"
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    # ignored but accepted so clients don't error
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    stop: list[str] | str | None = None


class ChoiceDelta(BaseModel):
    role: str | None = None
    content: str | None = None


class StreamChoice(BaseModel):
    index: int = 0
    delta: ChoiceDelta
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list[StreamChoice]


class Choice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage


# --------------------------------------------------------------------------- #
# Agent cache — one agent per (model, agent_type) pair                        #
# --------------------------------------------------------------------------- #

_agent_cache: dict[str, Any] = {}


def _get_agent(model_id: str, agent_type: AgentType, temperature: float) -> Any:
    key = f"{model_id}:{agent_type.value}:{temperature}"
    if key not in _agent_cache:
        logger.info("Creating agent for key=%s", key)
        cfg = OllamaConfig(
            model=model_id,
            agent_type=agent_type,
            temperature=temperature,
        )
        _agent_cache[key] = create_agent(cfg)
    return _agent_cache[key]


def _resolve_model(requested: str) -> tuple[str, AgentType]:
    """
    code: prefix → CodeAgent   (for actual coding/tool tasks)
    tool: prefix → ToolCallingAgent
    anything else → direct model call, no agent loop
    """
    if requested.startswith("code:"):
        return requested[5:], AgentType.CODE
    if requested.startswith("tool:"):
        return requested[5:], AgentType.TOOL_CALLING
    # bare model name or "agent" → direct, no ReAct loop
    if requested == "agent":
        return "qwen2.5-coder:7b", None  # None = direct call
    return requested, None


def _extract_prompt(messages: list[ChatMessage]) -> str:
    """Collapse the message list into a single prompt string for the agent."""
    parts = []
    for m in messages:
        if m.content:
            if m.role == "system":
                parts.append(f"[System]: {m.content}")
            elif m.role == "user":
                parts.append(m.content)
            elif m.role == "assistant":
                parts.append(f"[Assistant]: {m.content}")
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- #
# Routes                                                                       #
# --------------------------------------------------------------------------- #

@app.get("/v1/models")
async def list_models() -> dict:
    """Return a model list so clients like Continue can populate their picker."""
    now = int(time.time())
    models = [
        # Convenience aliases
        {"id": "agent",                     "object": "model", "created": now, "owned_by": "ollama-agent"},
        {"id": "code:qwen2.5-coder:14b",    "object": "model", "created": now, "owned_by": "ollama-agent"},
        {"id": "code:qwen2.5-coder:7b",     "object": "model", "created": now, "owned_by": "ollama-agent"},
        {"id": "tool:qwen3:8b",             "object": "model", "created": now, "owned_by": "ollama-agent"},
        {"id": "tool:qwen3.5:9b",           "object": "model", "created": now, "owned_by": "ollama-agent"},
    ]
    return {"object": "list", "data": models}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    model_id, agent_type = _resolve_model(req.model)
    temperature = req.temperature if req.temperature is not None else 0.0
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    if agent_type is None:
        # Direct model call — no agent loop, just forward to Ollama
        result = await _direct_model_call(model_id, req.messages, temperature, req.max_tokens)
    else:
        try:
            agent = _get_agent(model_id, agent_type, temperature)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Failed to initialise agent: {exc}") from exc

        prompt = _extract_prompt(req.messages)
        try:
            result: str = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, lambda: str(agent.run(prompt))
                ),
                timeout=300.0,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Agent timed out")
        except Exception as exc:
            logger.exception("Agent error")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    if req.stream:
        return StreamingResponse(
            _stream_response(result, completion_id, created, req.model),
            media_type="text/event-stream",
        )

    return ChatCompletionResponse(
        id=completion_id,
        created=created,
        model=req.model,
        choices=[Choice(message=ChatMessage(role="assistant", content=result))],
        usage=Usage(),
    )


async def _direct_model_call(
    model_id: str,
    messages: list[ChatMessage],
    temperature: float,
    max_tokens: int | None,
) -> str:
    """Call Ollama directly via httpx — no agent loop."""
    from ollama_agent.config import OllamaConfig
    cfg = OllamaConfig()

    payload = {
        "model": model_id,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "temperature": temperature,
        "max_tokens": max_tokens or 2048,
        "stream": False,
    }

    import httpx
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            f"{cfg.base_url.rstrip('/')}/v1/chat/completions",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def _stream_response(
    text: str,
    completion_id: str,
    created: int,
    model: str,
) -> AsyncGenerator[str, None]:
    """Yield the result word-by-word so streaming clients stay happy."""
    # Opening chunk with role
    yield _sse(ChatCompletionChunk(
        id=completion_id, created=created, model=model,
        choices=[StreamChoice(delta=ChoiceDelta(role="assistant", content=""))],
    ))

    # Stream word by word
    words = text.split(" ")
    for i, word in enumerate(words):
        chunk = word if i == len(words) - 1 else word + " "
        yield _sse(ChatCompletionChunk(
            id=completion_id, created=created, model=model,
            choices=[StreamChoice(delta=ChoiceDelta(content=chunk))],
        ))
        await asyncio.sleep(0)  # yield control back to event loop

    # Closing chunk
    yield _sse(ChatCompletionChunk(
        id=completion_id, created=created, model=model,
        choices=[StreamChoice(delta=ChoiceDelta(), finish_reason="stop")],
    ))
    yield "data: [DONE]\n\n"


def _sse(chunk: ChatCompletionChunk) -> str:
    return f"data: {chunk.model_dump_json()}\n\n"


# --------------------------------------------------------------------------- #
# Entrypoint                                                                   #
# --------------------------------------------------------------------------- #

def serve(host: str = "0.0.0.0", port: int = 8000, reload: bool = False) -> None:
    import uvicorn
    uvicorn.run("ollama_agent.server:app", host=host, port=port, reload=reload)