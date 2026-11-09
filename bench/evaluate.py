import json
import re
from decimal import Decimal, InvalidOperation

GSM8K_FINAL_ANSWER = re.compile(r"####\s*(-?\d[\d,]*(?:\.\d+)?)")


def normalize_number(value):
    try:
        return format(Decimal(value.replace(",", "")).normalize(), "f")
    except (InvalidOperation, AttributeError):
        return None


def extract_gsm8k_answer(text):
    matches = GSM8K_FINAL_ANSWER.findall(text)
    return normalize_number(matches[-1]) if matches else None


def score_gsm8k(examples, predictions):
    if len(examples) != len(predictions):
        raise ValueError("Every GSM8K example must have exactly one prediction")
    correct = sum(
        extract_gsm8k_answer(prediction) is not None
        and extract_gsm8k_answer(prediction) == normalize_number(example["expected"])
        for example, prediction in zip(examples, predictions)
    )
    total = len(examples)
    return {
        "accuracy_exact_match": correct / total if total else None,
        "correct": correct,
        "n_samples": total,
    }


def parse_judge_response(content):
    try:
        result = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("Judge response must be a JSON object") from error
    score = result.get("score") if isinstance(result, dict) else None
    if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
        raise ValueError("Judge score must be an integer from 1 to 5")
    reason = result.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Judge response must include a non-empty reason")
    return {"score": score, "reason": reason.strip()}


def score_judge(scores, task_types=None):
    valid_scores = [score for score in scores if isinstance(score, int) and not isinstance(score, bool) and 1 <= score <= 5]
    result = {
        "accuracy_judge_mean": sum(valid_scores) / len(valid_scores) if valid_scores else None,
        "n_samples": len(valid_scores),
    }
    if task_types is not None:
        grouped = {}
        for score, task_type in zip(scores, task_types):
            if isinstance(score, int) and not isinstance(score, bool) and 1 <= score <= 5:
                grouped.setdefault(task_type, []).append(score)
        result["by_task_type"] = {
            task_type: {"accuracy_judge_mean": sum(values) / len(values), "n_samples": len(values)}
            for task_type, values in sorted(grouped.items())
        }
    return result