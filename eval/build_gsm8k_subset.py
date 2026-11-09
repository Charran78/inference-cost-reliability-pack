import hashlib
import json
import random
import re
import urllib.request
from pathlib import Path

SOURCE_COMMIT = "b0bb162abedc65e1fdd8e93ed090fd7598ee68bc"
SOURCE_URL = (
    "https://raw.githubusercontent.com/openai/grade-school-math/"
    f"{SOURCE_COMMIT}/grade_school_math/data/test.jsonl"
)
SAMPLE_SIZE = 200
SAMPLE_SEED = 42
FINAL_ANSWER = re.compile(r"####\s*(-?\d[\d,]*)\s*$")
FILTER_VERSION = "gsm8k-test-v1"
EVAL_DIR = Path(__file__).resolve().parent


def build_subset():
    output_path = EVAL_DIR / "gsm8k_200.jsonl"
    manifest_path = EVAL_DIR / "gsm8k_200.manifest.json"
    if output_path.is_file() and manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        output_hash = hashlib.sha256(output_path.read_bytes()).hexdigest()
        if (
            manifest.get("source_commit") == SOURCE_COMMIT
            and manifest.get("sample_size") == SAMPLE_SIZE
            and manifest.get("filter_version") == FILTER_VERSION
            and manifest.get("subset_sha256") == output_hash
        ):
            print(f"Using verified {SAMPLE_SIZE}-example GSM8K subset at {output_path}")
            return

    with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
        source_bytes = response.read()
    source_lines = source_bytes.decode("utf-8").splitlines()
    records = [json.loads(line) for line in source_lines if line.strip()]
    eligible = []
    excluded_empty_question = 0
    excluded_invalid_answer = 0
    excluded_duplicate_question = 0
    seen_questions = set()
    for source_index, record in enumerate(records):
        question = record.get("question", "").strip()
        answer = record.get("answer", "")
        if not question:
            excluded_empty_question += 1
            continue
        normalized_question = " ".join(question.casefold().split())
        if normalized_question in seen_questions:
            excluded_duplicate_question += 1
            continue
        match = FINAL_ANSWER.search(answer)
        if not match:
            excluded_invalid_answer += 1
            continue
        seen_questions.add(normalized_question)
        eligible.append((source_index, question, match.group(1).replace(",", "")))
    if len(eligible) < SAMPLE_SIZE:
        raise ValueError(f"Expected at least {SAMPLE_SIZE} eligible examples, received {len(eligible)}")

    selected = sorted(random.Random(SAMPLE_SEED).sample(eligible, SAMPLE_SIZE), key=lambda row: row[0])
    subset = []
    for source_index, question, expected in selected:
        subset.append({
            "id": f"gsm8k-test-{source_index:04d}",
            "source_index": source_index,
            "prompt": question
            + "\nSolve the problem and end with the final answer in the format #### <number>.",
            "expected": expected,
        })

    output_bytes = ("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in subset)).encode("utf-8")
    output_path.write_bytes(output_bytes)
    manifest = {
        "source": "openai/grade-school-math, test split",
        "source_url": SOURCE_URL,
        "source_commit": SOURCE_COMMIT,
        "source_license": "MIT",
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "sample_size": SAMPLE_SIZE,
        "sample_seed": SAMPLE_SEED,
        "filter_version": FILTER_VERSION,
        "filter_counts": {
            "source_rows": len(records),
            "eligible_rows": len(eligible),
            "excluded_empty_question": excluded_empty_question,
            "excluded_invalid_final_answer": excluded_invalid_answer,
            "excluded_duplicate_question": excluded_duplicate_question,
        },
        "selected_source_indices": [row[0] for row in selected],
        "subset_sha256": hashlib.sha256(output_bytes).hexdigest(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {len(subset)} examples to {output_path}")


if __name__ == "__main__":
    build_subset()