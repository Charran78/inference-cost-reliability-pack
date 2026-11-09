import os
import re

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

LARGE_URL = os.getenv("LARGE_URL", "http://vllm-large:8000")
SMALL_URL = os.getenv("SMALL_URL", "http://vllm-small:8000")
LARGE_MODEL = os.getenv("LARGE_MODEL", "large")
SMALL_MODEL = os.getenv("SMALL_MODEL", "small")
SMALL_MAX_CHARS = int(os.getenv("SMALL_MAX_CHARS", "220"))
COMPLEXITY_TERMS = re.compile(r"\b(explain|compare|analy[sz]e|why|derive|prove|step by step)\b", re.I)
app = FastAPI()
client = httpx.AsyncClient(timeout=None)


@app.on_event("shutdown")
async def close_client():
    await client.aclose()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def completions(request: Request):
    body = await request.json()
    text = " ".join(str(message.get("content", "")) for message in body.get("messages", []))
    simple = len(text) <= SMALL_MAX_CHARS and not COMPLEXITY_TERMS.search(text)
    target = SMALL_URL if simple else LARGE_URL
    body["model"] = SMALL_MODEL if simple else LARGE_MODEL
    try:
        upstream = await client.send(
            client.build_request("POST", f"{target}/v1/chat/completions", json=body),
            stream=True,
        )
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"upstream unavailable: {error}") from error
    if upstream.is_error:
        detail = await upstream.aread()
        await upstream.aclose()
        raise HTTPException(status_code=upstream.status_code, detail=detail.decode(errors="replace"))

    async def events():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        events(),
        media_type=upstream.headers.get("content-type", "text/event-stream"),
        headers={"X-Routed-Model": "small" if simple else "large"},
    )