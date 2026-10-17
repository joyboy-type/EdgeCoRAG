"""Independent no-judge metric projection; no research data or network on import.

Reference: MMDocRAG/MMDocRAG@2fd7505c6a576376b4a92aafaff6d87494765bb7.
Not an official evaluator, paper-table reproduction, or runtime-v1.10.1 scorer.
Missing predictions are packaging errors. Explicit generation failures stay in N.
"""
import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re

SCORER_ID = "b_mmdocrag_nojudge_metrics_v1"
UPSTREAM_COMMIT = "2fd7505c6a576376b4a92aafaff6d87494765bb7"
UPSTREAM_EVAL_SHA256 = "b229d038c4015ec1f6783129d58a8db824ee93c6473e2e87435d5bec35797b11"
QUOTE_ID = re.compile(r"(?:text|image)\d+\Z")
JUDGE_DIMENSIONS = ("Fluency", "Citation Quality", "Text-Image Coherence", "Reasoning Logic", "Factuality")


class ContractError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def extract_citations(text):
    texts = list(dict.fromkeys("text" + x for x in re.findall(r"\[(\d+)\]", text)))
    images = list(dict.fromkeys("image" + x for x in re.findall(r"\(image(\d+)\)", text)))
    return texts, images, texts + images


def get_scores(gold, predicted):
    g, p = set(gold), set(predicted)
    tp, fp, fn = len(g & p), len(p - g), len(g - p)
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def process_response(raw):
    # Source replaces every falsy value with one space. Truthy non-text is invalid.
    if raw and not isinstance(raw, str):
        raise ContractError("Truthy response must be text")
    before = raw if raw else " "
    if "</think>\n\n" in before:
        return before, before.split("</think>\n\n")[1], "exact_think_split_index1"
    if " seconds\n\n" in before:
        return before, before.split(" seconds\n\n")[1], "exact_seconds_split_index1"
    return before, before, "unchanged"


def ordered_index(rows, expected, qid_type, name):
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise ContractError(name + ": whole-list length mismatch; no partial score")
    result, order = {}, []
    for row in rows:
        if not isinstance(row, dict) or "q_id" not in row:
            raise ContractError(name + ": q_id object required")
        q = row["q_id"]
        if type(q) is not qid_type or (qid_type is str and not q.strip()):
            raise ContractError(name + ": frozen qid type/nonempty rule violated")
        if q in result:
            raise ContractError(name + ": duplicate qid")
        result[q] = row
        order.append(q)
    if set(result) != set(expected):
        raise ContractError(name + ": missing/unknown qid; no partial score")
    return [result[q] for q in expected], {
        "count": len(rows), "input_qid_order": order,
        "aligned_qid_order": expected, "reordered": order != expected,
        "input_order_sha256": digest(order), "aligned_order_sha256": digest(expected),
    }


def align_inputs(manifest, gold, predictions, pools):
    if not isinstance(manifest, dict):
        raise ContractError("Independent frozen manifest required")
    kind = manifest.get("qid_type")
    if kind not in ["str", "int"]:
        raise ContractError("Explicit frozen qid_type=str or int required")
    qtype = {"str": str, "int": int}[kind]
    qids = manifest.get("qids")
    if not isinstance(qids, list) or not qids:
        raise ContractError("Nonempty frozen qid list required")
    if any(type(q) is not qtype or (qtype is str and not q.strip()) for q in qids):
        raise ContractError("Frozen qid types are inconsistent")
    if len(set(qids)) != len(qids):
        raise ContractError("Duplicate qid in frozen manifest")
    for key in ["dataset_revision", "split", "setting"]:
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise ContractError("Manifest must fix " + key)
    aligned, audit = [], {}
    for name, rows in [("gold", gold), ("predictions", predictions), ("pools", pools)]:
        data, receipt = ordered_index(rows, qids, qtype, name)
        aligned.append(data)
        audit[name] = receipt
    return qids, aligned, audit


def quote_list(value, name):
    if not isinstance(value, list) or any(not isinstance(x, str) or not QUOTE_ID.fullmatch(x) for x in value):
        raise ContractError(name + ": quote ID list must use textN/imageN")
    return value


def token_summary(predictions, qids):
    pairs, missing, invalid = [], [], []
    for q, row in zip(qids, predictions):  # Full length/set alignment already proved.
        absent = [k for k in ["in_tok", "out_tok"] if k not in row]
        bad = [k for k in ["in_tok", "out_tok"] if k in row and
               (type(row[k]) is not int or row[k] < 0)]
        if absent:
            missing.append({"q_id": q, "fields": absent})
        if bad:
            invalid.append({"q_id": q, "fields": bad})
        if not absent and not bad:
            pairs.append((row["in_tok"], row["out_tok"]))
    complete = len(pairs) == len(qids)
    return {"status": "complete" if complete else "invalid_or_incomplete",
            "fixed_denominator": len(qids), "complete_pairs": len(pairs),
            "missing": missing, "invalid": invalid,
            "mean_input_tokens": sum(x[0] for x in pairs) / len(qids) if complete else None,
            "mean_output_tokens": sum(x[1] for x in pairs) / len(qids) if complete else None,
            "subset_mean_reported": False, "imputed_tokens": False,
            "upstream_difference": "No division by zero or hidden available-pair denominator."}


class LexicalMetrics:
    """Local installed libraries/resources only; no fallback tokenizer/download."""
    def __init__(self):
        self.bleu = self.rouge = None
        self.dependencies, self.unavailable = {}, {}
        for distribution in ["nltk", "rouge-score"]:
            try:
                self.dependencies[distribution] = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                self.dependencies[distribution] = None
        if self.dependencies["nltk"]:
            try:
                from nltk.tokenize import word_tokenize
                from nltk.translate.bleu_score import sentence_bleu
                word_tokenize("Synthetic resource probe only.")
                self.bleu = lambda reference, candidate: sentence_bleu(
                    [word_tokenize(reference)], word_tokenize(candidate))
            except LookupError:
                self.unavailable["bleu"] = "Local NLTK tokenizer resource missing; not downloaded; no tokenizer substitution"
            except ImportError as e:
                self.unavailable["bleu"] = type(e).__name__ + ": " + str(e)
        else:
            self.unavailable["bleu"] = "NLTK not installed; not installed automatically"
        if self.dependencies["rouge-score"]:
            try:
                from rouge_score import rouge_scorer
                scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
                self.rouge = lambda reference, candidate: scorer.score(reference, candidate)["rougeL"].fmeasure
            except ImportError as e:
                self.unavailable["rougeL"] = type(e).__name__ + ": " + str(e)
        else:
            self.unavailable["rougeL"] = "rouge-score not installed; not installed automatically"


def validate_judge_rows(rows, manifest):
    """Structure-only contract guard for synthetic tests; never evaluate a judge."""
    qtype = {"str": str, "int": int}[manifest["qid_type"]]
    aligned, audit = ordered_index(rows, manifest["qids"], qtype, "judge")
    for row in aligned:
        value = row.get("response")
        if not isinstance(value, dict) or set(value) != set(JUDGE_DIMENSIONS):
            raise ContractError("Judge requires all five dimensions; no missing->zero default")
        for number in value.values():
            if type(number) not in [int, float] or not math.isfinite(number) or not 0 <= number <= 5:
                raise ContractError("Judge values must be finite numeric0..5")
    return {"status": "validated_only_not_evaluated", "alignment": audit}


def score(manifest, gold, predictions, pools):
    qids, (gold, predictions, pools), alignment = align_inputs(manifest, gold, predictions, pools)
    # Validate all packaging before constructing any score or importing metrics.
    for g, pred, pool in zip(gold, predictions, pools):
        refs = quote_list(g.get("gold_quotes"), "gold")
        available = quote_list(pool.get("quote_ids"), "pool")
        if len(set(available)) != len(available):
            raise ContractError("Duplicate quote ID in candidate pool")
        if not set(refs) <= set(available):
            raise ContractError("Unknown gold quote ID outside the fixed candidate pool")
        if not isinstance(g.get("answer_interleaved"), str):
            raise ContractError("Gold reference answer must be text")
        if "response" not in pred:
            raise ContractError("Prediction requires response even for a failed generation")
        process_response(pred["response"])
        if pred.get("generation_status", "completed") not in ["completed", "failed", "generation_failed", "input_failed"]:
            raise ContractError("Unknown generation status; do not guess failure policy")
        if pred.get("generation_error") is not None and not isinstance(pred["generation_error"], str):
            raise ContractError("generation_error must be text or null")
        if "truncated" in pred and type(pred["truncated"]) is not bool:
            raise ContractError("truncated must be an explicit boolean")
        if pred.get("termination_reason") is not None and not isinstance(pred["termination_reason"], str):
            raise ContractError("termination_reason must be text or null")
    lexical = LexicalMetrics()
    rows, gold_text, gold_image, pred_text, pred_image = [], [], [], [], []
    lexical_values = {"bleu": [], "rougeL": []}
    for q, g, pred, pool in zip(qids, gold, predictions, pools):
        failed = pred.get("generation_status", "completed") != "completed" or bool(pred.get("generation_error"))
        effective = "" if failed else pred["response"]
        before, processed, processing = process_response(effective)
        text, image, union = extract_citations(processed)
        available = set(pool["quote_ids"])
        item = {"q_id": q, "response_raw": pred["response"], "response_before_thinking": before,
                "response_processed": processed, "processing": processing,
                "generation_status": pred.get("generation_status", "completed"),
                "generation_error": pred.get("generation_error"), "failure_scored_as_empty": failed,
                "termination_reason": pred.get("termination_reason"),
                "truncated": bool(pred.get("truncated", False)),
                "truncation_policy": "Preserve partial response unless explicitly failed; new research execution protocol still pending",
                "gold_quotes_order": list(g["gold_quotes"]), "pool_quote_ids_order": list(pool["quote_ids"]),
                "predicted_quotes": union, "out_of_pool_quotes": [x for x in union if x not in available],
                "citation": get_scores(g["gold_quotes"], union), "bleu": None, "rougeL": None}
        for x in g["gold_quotes"]:
            (gold_text if x.startswith("text") else gold_image).append(str(q) + x)
        pred_text.extend(str(q) + x for x in text)
        pred_image.extend(str(q) + x for x in image)
        for name, function in [("bleu", lexical.bleu), ("rougeL", lexical.rouge)]:
            if function is not None:
                try:
                    value = function(g["answer_interleaved"], processed)
                    if not math.isfinite(value):
                        raise ValueError("Nonfinite lexical score")
                    item[name] = value
                    lexical_values[name].append(value)
                except (LookupError, ValueError, TypeError) as e:
                    item[name + "_error"] = type(e).__name__ + ": " + str(e)
        rows.append(item)
    n = len(qids)
    modalities = {"text": get_scores(gold_text, pred_text), "image": get_scores(gold_image, pred_image)}
    for mode in modalities:
        modalities[mode]["questions_with_gold"] = sum(any(x.startswith(mode) for x in g["gold_quotes"]) for g in gold)
        modalities[mode]["fixed_question_denominator"] = n
    overall = sum(r["citation"]["f1"] for r in rows) / n
    lexical_report = {}
    for name in ["bleu", "rougeL"]:
        measured = lexical_values[name]
        complete = len(measured) == n
        lexical_report[name] = {"status": "evaluated" if complete else "not_fully_evaluated",
            "fixed_denominator": n, "measured_questions": len(measured),
            "macro_mean": sum(measured) / n if complete else None,
            "missing_reason": lexical.unavailable.get(name),
            "per_question_errors": [{"q_id": r["q_id"], "error": r[name + "_error"]} for r in rows if name + "_error" in r],
            "subset_mean_reported": False}
    return {"scorer_id": SCORER_ID, "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "status": "metrics_evaluated" if all(x["macro_mean"] is not None for x in lexical_report.values()) else "partial_metrics_dependencies_unverified",
        "upstream_commit": UPSTREAM_COMMIT, "upstream_eval_sha256": UPSTREAM_EVAL_SHA256,
        "input_identity": {k: manifest[k] for k in ["dataset_revision", "split", "setting", "qid_type", "qids"]},
        "synthetic": manifest.get("synthetic", False), "manifest_sha256": digest(manifest), "alignment": alignment,
        "fixed_denominator": n, "explicit_generation_failures": sum(r["failure_scored_as_empty"] for r in rows),
        "empty_processed_responses": sum(not r["response_processed"].strip() for r in rows),
        "out_of_pool_quote_count": sum(len(r["out_of_pool_quotes"]) for r in rows),
        "code_compatible_overall_union_macro_f1": {"ratio": overall, "percent": overall * 100, "denominator": n},
        "code_compatible_modality_global": modalities,
        "exploratory_mean_of_global_modality_f1": {"ratio": (modalities["text"]["f1"] + modalities["image"]["f1"]) / 2,
            "not_paper_table_reproduction": True,
            "note": "Paper prose describes modality averaging; released source Overall is per-question union macro F1. These names are not interchangeable."},
        "lexical": lexical_report, "dependencies": lexical.dependencies, "tokens": token_summary(predictions, qids),
        "judge": {"status": "not_evaluated", "dimensions": {k: None for k in JUDGE_DIMENSIONS}},
        "per_question": rows, "full_official_evaluation_reproduced": False,
        "research_schema_verified": False, "external_dataset_validation_completed": False}


def no_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ContractError("Duplicate JSON object key: " + key)
        value[key] = item
    return value


def load_input(path):
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    if path.suffix.lower() == ".jsonl":
        value = [json.loads(line, object_pairs_hook=no_duplicate_keys) for line in text.splitlines() if line.strip()]
    else:
        value = json.loads(text, object_pairs_hook=no_duplicate_keys)
    return value, {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ["manifest", "gold", "predictions", "pools", "output"]:
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    # Exclusive output: no existing result or runtime-v1.10.1 file can be replaced.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as out:
        try:
            loaded, pins = {}, {}
            for key in ["manifest", "gold", "predictions", "pools"]:
                loaded[key], pins[key] = load_input(getattr(args, key))
            result = score(**loaded)
            result["input_file_pins"] = pins
            code = 0
        except (ValueError, TypeError, KeyError, OSError) as error:
            result = {"scorer_id": SCORER_ID, "status": "scoring_not_ready", "scores": None,
                      "error": type(error).__name__ + ": " + str(error),
                      "judge": {"status": "not_evaluated"}, "no_partial_denominator_score": True}
            code = 2
        json.dump(result, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
