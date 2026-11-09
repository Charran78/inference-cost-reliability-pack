import asyncio
import hashlib
import json
import math
import os
import platform
import re
import statistics
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
try:
    from .evaluate import extract_gsm8k_answer, parse_judge_response, score_gsm8k, score_judge
except ImportError:
    from evaluate import extract_gsm8k_answer, parse_judge_response, score_gsm8k, score_judge

ROOT = Path(__file__).resolve().parents[1]
CONCURRENCIES = (1, 8, 32, 64)
CONFIGS = {
    "fp16_naive": {"url": os.getenv("BASELINE_URL", "http://localhost:8000"), "model": "baseline"},
    "fp8_vllm": {"url": os.getenv("FP8_URL", "http://localhost:8001"), "model": "large"},
    "fp8_vllm_router": {"url": os.getenv("ROUTER_URL", "http://localhost:8003"), "model": "router"},
}
GPU_HANDLE = None


def init_gpu_monitor():
    global GPU_HANDLE
    try:
        import pynvml

        pynvml.nvmlInit()
        GPU_HANDLE = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(GPU_HANDLE)
        return name.decode() if isinstance(name, bytes) else name
    except Exception:
        return None


def gpu_memory_mb():
    if GPU_HANDLE is None:
        return None
    try:
        import pynvml

        return pynvml.nvmlDeviceGetMemoryInfo(GPU_HANDLE).used / (1024 * 1024)
    except Exception:
        return None


def percentile(values, percentile_value):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * percentile_value) - 1)]


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_dataset():
    path = Path(os.getenv("EVAL_DATASET", str(ROOT / "eval/subset.jsonl")))
    return load_jsonl(path)


def parse_sse_line(line):
    if not line.startswith("data: ") or line == "data: [DONE]":
        return None
    try:
        return json.loads(line[6:])
    except json.JSONDecodeError:
        return None


async def request_completion(client, url, model, prompt, max_tokens):
    started = time.perf_counter()
    first_token = None
    chunk_times = []
    text_parts = []
    token_count = 0
    async with client.stream(
        "POST",
        f"{url}/v1/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        },
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            event = parse_sse_line(line)
            if not event:
                continue
            choices = event.get("choices", [])
            if choices:
                content = choices[0].get("delta", {}).get("content", "")
                if content:
                    now = time.perf_counter()
                    first_token = first_token or now
                    chunk_times.append(now)
                    text_parts.append(content)
            usage = event.get("usage") or {}
            token_count = usage.get("completion_tokens", token_count)
    ended = time.perf_counter()
    return {
        "ttft_ms": (first_token - started) * 1000 if first_token else None,
        "itl_ms": [(right - left) * 1000 for left, right in zip(chunk_times, chunk_times[1:])],
        "elapsed_s": ended - started,
        "completion_tokens": token_count,
        "text": "".join(text_parts),
    }


async def run_load_test(url, model, dataset, concurrency, request_count, max_tokens):
    semaphore = asyncio.Semaphore(concurrency)
    started = time.perf_counter()
    memory_samples = []
    initial_memory = gpu_memory_mb()
    if initial_memory is not None:
        memory_samples.append(initial_memory)
    stop_sampling = threading.Event()

    def sample_memory():
        while not stop_sampling.is_set():
            value = gpu_memory_mb()
            if value is not None:
                memory_samples.append(value)
            stop_sampling.wait(0.1)

    monitor = threading.Thread(target=sample_memory, daemon=True)
    monitor.start()

    async def run_one(index):
        prompt = dataset[index % len(dataset)]["prompt"]
        async with semaphore:
            return await request_completion(client, url, model, prompt, max_tokens)

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            results = await asyncio.gather(*(run_one(index) for index in range(request_count)))
    finally:
        stop_sampling.set()
        monitor.join()
    elapsed = time.perf_counter() - started
    total_tokens = sum(result["completion_tokens"] for result in results)
    ttfts = [result["ttft_ms"] for result in results if result["ttft_ms"] is not None]
    itls = [value for result in results for value in result["itl_ms"]]
    hourly_rate = float(os.environ["GPU_HOURLY_USD"]) if os.getenv("GPU_HOURLY_USD") else None
    throughput = total_tokens / elapsed if elapsed else 0
    return {
        "concurrency": concurrency,
        "requests": request_count,
        "elapsed_s": elapsed,
        "output_tokens": total_tokens,
        "throughput_tok_s": throughput,
        "ttft_p50_ms": percentile(ttfts, 0.50),
        "ttft_p95_ms": percentile(ttfts, 0.95),
        "itl_p50_ms": statistics.median(itls) if itls else None,
        "vram_peak_mb": max(memory_samples) if memory_samples else None,
        "cost_usd_per_million_tokens": hourly_rate * 1_000_000 / (throughput * 3600) if hourly_rate and throughput else None,
    }


async def run_gsm8k_quality(url, model, dataset, max_tokens, concurrency):
    semaphore = asyncio.Semaphore(concurrency)

    async def predict(client, example):
        async with semaphore:
            result = await request_completion(client, url, model, example["prompt"], max_tokens)
            return result["text"]

    async with httpx.AsyncClient(timeout=None) as client:
        predictions = await asyncio.gather(*(predict(client, example) for example in dataset))
    summary = score_gsm8k(dataset, predictions)
    summary["samples"] = [
        {
            "id": example["id"],
            "expected": example["expected"],
            "predicted": extract_gsm8k_answer(prediction),
            "correct": (
                extract_gsm8k_answer(prediction) is not None
                and extract_gsm8k_answer(prediction) == example["expected"]
            ),
        }
        for example, prediction in zip(dataset, predictions)
    ]
    return summary


def domain_prompt(example):
    question = example["prompt"].strip()
    if example.get("context"):
        question = f"Context:\n{example['context'].strip()}\n\nPrompt:\n{question}"
    return question


async def run_domain_quality(url, model, dataset, max_tokens, concurrency, judge_base_url, judge_model,
                             judge_api_key, judge_prompt, rubric_template):
    metadata = {
        "accuracy_judge_mean": None,
        "n_samples": 0,
        "delta_vs_baseline": None,
        "judge_model": judge_model or None,
        "judge_prompt_sha256": hashlib.sha256(judge_prompt.encode("utf-8")).hexdigest(),
        "status": None,
        "requested_samples": len(dataset),
        "by_task_type": {},
        "samples": [],
    }
    if not dataset:
        return {**metadata, "status": "not_configured"}
    if not judge_base_url or not judge_model:
        return {**metadata, "status": "judge_not_configured", "requested_samples": len(dataset)}

    semaphore = asyncio.Semaphore(concurrency)

    async def evaluate_one(model_client, judge_client, example):
        async with semaphore:
            generated = await request_completion(
                model_client, url, model, domain_prompt(example), max_tokens
            )
            task_type = example["task_type"]
            task_rubric = rubric_template["task_types"][task_type]
            system_prompt = "\n\n".join([
                judge_prompt,
                f"Task type: {task_type}",
                "Score scale:\n" + json.dumps(rubric_template["score_scale"], ensure_ascii=False),
                "Global rules:\n- " + "\n- ".join(rubric_template["global_rules"]),
                "Task-specific criteria:\n- " + "\n- ".join(task_rubric["criteria"]),
            ])
            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps({
                        "prompt": example["prompt"],
                        "context": example.get("context", ""),
                        "expected_output": example["expected_output"],
                        "candidate_output": generated["text"],
                    }, ensure_ascii=False),
                },
            ]
            headers = {"Authorization": f"Bearer {judge_api_key}"} if judge_api_key else {}
            response = await judge_client.post(
                f"{judge_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": judge_model,
                    "messages": messages,
                    "temperature": 0,
                    "stream": False,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            score = parse_judge_response(content)
            return {"id": example["id"], "task_type": task_type, **score}

    async with httpx.AsyncClient(timeout=None) as model_client, httpx.AsyncClient(timeout=120) as judge_client:
        samples = await asyncio.gather(
            *(evaluate_one(model_client, judge_client, example) for example in dataset)
        )
    summary = score_judge(
        [sample["score"] for sample in samples],
        [sample["task_type"] for sample in samples],
    )
    return {**metadata, **summary, "status": "measured", "samples": samples}


def add_quality_deltas(results):
    baseline = results["fp16_naive"]["quality"]
    for config in results.values():
        quality = config["quality"]
        gsm_accuracy = quality["gsm8k"]["accuracy_exact_match"]
        baseline_accuracy = baseline["gsm8k"]["accuracy_exact_match"]
        if gsm_accuracy is not None and baseline_accuracy is not None:
            quality["gsm8k"]["delta_vs_baseline_pp"] = round((gsm_accuracy - baseline_accuracy) * 100, 2)
        domain_mean = quality["domain"]["accuracy_judge_mean"]
        baseline_mean = baseline["domain"]["accuracy_judge_mean"]
        if domain_mean is not None and baseline_mean is not None:
            quality["domain"]["delta_vs_baseline"] = round(domain_mean - baseline_mean, 3)


def create_report_template():
    load_test = {
        "concurrency": None,
        "requests": None,
        "elapsed_s": None,
        "output_tokens": None,
        "throughput_tok_s": None,
        "ttft_p50_ms": None,
        "ttft_p95_ms": None,
        "itl_p50_ms": None,
        "vram_peak_mb": None,
        "cost_usd_per_million_tokens": None,
    }
    return {
        "created_at": None,
        "models": {
            "baseline_and_fp8": "meta-llama/Meta-Llama-3.1-8B-Instruct",
            "router_small": "Qwen/Qwen2.5-3B-Instruct",
        },
        "benchmark_workload_dataset": None,
        "benchmark_workload_examples": None,
        "evaluation": {
            "gsm8k_dataset": None,
            "gsm8k_examples": None,
            "gsm8k_manifest": None,
            "domain_dataset": None,
            "domain_examples": None,
            "judge_model": None,
            "judge_prompt_sha256": None,
            "rubric_template_sha256": None,
        },
        "hourly_gpu_cost_usd": None,
        "system": {"platform": None, "python": None, "gpu_name": None},
        "results": {
            name: {
                "load_tests": [{**load_test} for _ in CONCURRENCIES],
                "quality": {
                    "gsm8k": {
                        "accuracy_exact_match": None,
                        "correct": None,
                        "n_samples": None,
                        "samples": [],
                        "delta_vs_baseline_pp": None,
                    },
                    "domain": {
                        "accuracy_judge_mean": None,
                        "n_samples": None,
                        "delta_vs_baseline": None,
                        "judge_model": None,
                        "judge_prompt_sha256": None,
                        "status": None,
                        "requested_samples": None,
                        "by_task_type": {},
                        "samples": [],
                    },
                },
            }
            for name in CONFIGS
        },
    }


async def main():
    dataset = load_dataset()
    if not dataset:
        raise ValueError("Evaluation dataset is empty")
    gsm8k_path = Path(os.getenv("GSM8K_DATASET", str(ROOT / "eval/gsm8k_200.jsonl")))
    if not gsm8k_path.is_file():
        raise FileNotFoundError(f"GSM8K dataset missing; run `make eval-data` first: {gsm8k_path}")
    gsm8k_dataset = load_jsonl(gsm8k_path)
    domain_path = Path(os.getenv("DOMAIN_EVAL_DATASET", str(ROOT / "private_eval/domain_set.jsonl")))
    domain_dataset = load_jsonl(domain_path) if domain_path.is_file() else []
    request_count = max(int(os.getenv("BENCH_REQUESTS", "64")), max(CONCURRENCIES))
    max_tokens = int(os.getenv("BENCH_MAX_TOKENS", "64"))
    quality_max_tokens = int(os.getenv("QUALITY_MAX_TOKENS", "512"))
    eval_concurrency = int(os.getenv("EVAL_CONCURRENCY", "4"))
    judge_base_url = os.getenv("JUDGE_BASE_URL", "")
    judge_model = os.getenv("JUDGE_MODEL", "")
    judge_api_key = os.getenv("JUDGE_API_KEY", "")
    judge_prompt = (ROOT / "eval/judge_prompt.txt").read_text()
    rubric_template = json.loads((ROOT / "eval/rubric_template.json").read_text())
    report = create_report_template()
    report.update({
        "created_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_workload_dataset": str(Path(os.getenv("EVAL_DATASET", "eval/subset.jsonl"))),
        "benchmark_workload_examples": len(dataset),
        "hourly_gpu_cost_usd": float(os.environ["GPU_HOURLY_USD"]) if os.getenv("GPU_HOURLY_USD") else None,
        "system": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "gpu_name": init_gpu_monitor(),
        },
    })
    report["evaluation"].update({
        "gsm8k_dataset": str(gsm8k_path),
        "gsm8k_examples": len(gsm8k_dataset),
        "gsm8k_manifest": str(gsm8k_path.with_name("gsm8k_200.manifest.json")),
        "domain_dataset": str(domain_path) if domain_dataset else None,
        "domain_examples": len(domain_dataset),
        "judge_model": judge_model or None,
        "judge_prompt_sha256": hashlib.sha256(judge_prompt.encode("utf-8")).hexdigest(),
        "rubric_template_sha256": hashlib.sha256(
            (ROOT / "eval/rubric_template.json").read_bytes()
        ).hexdigest(),
    })
    for name, config in CONFIGS.items():
        url = config["url"]
        print(f"Benchmarking {name}", flush=True)
        report["results"][name]["quality"] = {
            "gsm8k": await run_gsm8k_quality(
                url, config["model"], gsm8k_dataset, quality_max_tokens, eval_concurrency
            ),
            "domain": await run_domain_quality(
                url,
                config["model"],
                domain_dataset,
                quality_max_tokens,
                eval_concurrency,
                judge_base_url,
                judge_model,
                judge_api_key,
                judge_prompt,
                rubric_template,
            ),
        }
        report["results"][name]["load_tests"] = []
        for concurrency in CONCURRENCIES:
            measurement = await run_load_test(url, config["model"], dataset, concurrency, request_count, max_tokens)
            report["results"][name]["load_tests"].append(measurement)
            print(f"  concurrency={concurrency}: {measurement['throughput_tok_s']:.2f} tok/s", flush=True)
    add_quality_deltas(report["results"])
    output = Path("/results/results.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {output}", flush=True)


if __name__ == "__main__":
    client = None
    asyncio.run(main())