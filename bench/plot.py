import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

COLORS = {"fp16_naive": "#b44b35", "fp8_vllm": "#267c78", "fp8_vllm_router": "#d29428"}
LABELS = {"fp16_naive": "FP16 naive", "fp8_vllm": "FP8 vLLM", "fp8_vllm_router": "FP8 vLLM + router"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="results/results.json")
    args = parser.parse_args()
    report = json.loads(Path(args.results).read_text())
    output_dir = Path(args.results).parent

    figure, axis = plt.subplots(figsize=(7, 4.5))
    for name, result in report["results"].items():
        measurement = next((item for item in result["load_tests"] if item["concurrency"] == 32), None)
        if measurement and measurement["cost_usd_per_million_tokens"] is not None:
            axis.scatter(measurement["ttft_p95_ms"], measurement["cost_usd_per_million_tokens"],
                         label=LABELS.get(name, name), color=COLORS.get(name))
    axis.set(xlabel="TTFT p95 (ms)", ylabel="USD por millón de tokens", title="Coste y latencia @ concurrencia 32")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_dir / "cost-latency.png", dpi=160)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(7, 4.5))
    for name, result in report["results"].items():
        tests = sorted(result["load_tests"], key=lambda item: item["concurrency"])
        axis.plot([item["concurrency"] for item in tests], [item["throughput_tok_s"] for item in tests],
                  marker="o", label=LABELS.get(name, name), color=COLORS.get(name))
    axis.set(xlabel="Concurrencia", ylabel="Tokens de salida / s", title="Throughput por concurrencia")
    axis.set_xticks([1, 8, 32, 64])
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_dir / "throughput-concurrency.png", dpi=160)
    plt.close(figure)


if __name__ == "__main__":
    main()