import json
import os
import queue
import threading
import uuid

import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from transformers import AutoModelForCausalLM, AutoTokenizer
from transformers.generation.streamers import BaseStreamer

MODEL_ID = os.getenv("MODEL_ID", "meta-llama/Meta-Llama-3.1-8B-Instruct")
app = FastAPI()
tokenizer = None
model = None


class TokenQueue(BaseStreamer):
    def __init__(self):
        self.items = queue.Queue()
        self.first = True

    def put(self, value):
        if self.first:
            self.first = False
            return
        for token_id in value.reshape(-1).tolist():
            self.items.put(token_id)

    def end(self):
        self.items.put(None)


@app.on_event("startup")
def load_model():
    global tokenizer, model
    if not torch.cuda.is_available():
        raise RuntimeError("The FP16 baseline requires a CUDA GPU")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, token=os.getenv("HF_TOKEN"))
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float16,
        device_map="cuda",
        token=os.getenv("HF_TOKEN"),
    )
    model.eval()


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_ID}


@app.post("/v1/chat/completions")
def completions(body: dict):
    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages must not be empty")
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    input_ids = tokenizer(prompt, return_tensors="pt").input_ids.to(model.device)
    streamer = TokenQueue()
    request_id = f"chatcmpl-{uuid.uuid4().hex}"
    max_tokens = min(int(body.get("max_tokens", 128)), 512)

    def generate():
        try:
            model.generate(
                input_ids,
                streamer=streamer,
                max_new_tokens=max_tokens,
                do_sample=float(body.get("temperature", 0)) > 0,
                temperature=max(float(body.get("temperature", 0.7)), 1e-5),
                pad_token_id=tokenizer.eos_token_id,
            )
        except Exception as error:
            streamer.items.put(error)
            streamer.end()

    def events():
        thread = threading.Thread(target=generate, daemon=True)
        thread.start()
        completion_tokens = 0
        try:
            while True:
                token_id = streamer.items.get()
                if token_id is None:
                    break
                if isinstance(token_id, Exception):
                    raise token_id
                text = tokenizer.decode([token_id], skip_special_tokens=True)
                if not text:
                    continue
                completion_tokens += 1
                chunk = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
            final = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": int(input_ids.shape[-1]), "completion_tokens": completion_tokens},
            }
            yield f"data: {json.dumps(final)}\n\ndata: [DONE]\n\n"
        finally:
            thread.join(timeout=1)

    return StreamingResponse(events(), media_type="text/event-stream")