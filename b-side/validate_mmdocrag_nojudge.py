"""T01-T15 synthetic contract checks; never read QA, images or saved model outputs."""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import mmdocrag_nojudge as adapter


def fixture(qids=None):
    qids = qids or ["synthetic:alpha"]
    manifest = {"qid_type": "str", "qids": qids, "dataset_revision": "SYNTHETIC_ONLY",
                "split": "synthetic", "setting": "synthetic_quotes", "synthetic": True}
    gold = [{"q_id": q, "gold_quotes": ["text1", "image2"],
             "answer_interleaved": "Fictional silver comet crosses four violet moons [1] (image2)"} for q in qids]
    predictions = [{"q_id": q, "response": "[1] (image2)", "in_tok": 12, "out_tok": 4} for q in qids]
    pools = [{"q_id": q, "quote_ids": ["text1", "image2"]} for q in qids]
    return manifest, gold, predictions, pools


def rejected(function):
    try:
        function()
    except adapter.ContractError:
        return
    raise AssertionError("Expected contract rejection")


def run(source):
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != adapter.UPSTREAM_EVAL_SHA256:
        raise ValueError("Fixed upstream source cache hash mismatch; no execution")
    tree = ast.parse(raw.decode("utf-8"))
    names = {"extract_citations", "get_scores"}
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in functions} != names:
        raise ValueError("Expected selected pure function definitions only")
    environment = {"re": re}
    # Execute only these two small stateless AST nodes. No upstream import or
    # top-level statements, tokenizer download, calculate_all or judge path.
    exec(compile(ast.Module(body=functions, type_ignores=[]), "selected_upstream_pure_functions", "exec"), environment)
    extract, original_scores = environment["extract_citations"], environment["get_scores"]
    results = []

    def case(name, fn):
        fn()
        results.append({"id": name, "status": "passed"})

    def result(data):
        return adapter.score(*data)

    def t01():
        r = result(fixture())
        assert r["code_compatible_overall_union_macro_f1"]["percent"] == 100
        assert r["per_question"][0]["citation"]["f1"] == 1
        assert r["judge"]["status"] == "not_evaluated" and all(x is None for x in r["judge"]["dimensions"].values())
    case("T01", t01)

    def t02():
        d = fixture(); d[2][0]["response"] = "[1] [1] (image2) (image2)"
        assert adapter.extract_citations(d[2][0]["response"]) == extract(d[2][0]["response"])
        assert result(d)["code_compatible_overall_union_macro_f1"]["ratio"] == 1
    case("T02", t02)

    def t03():
        d = fixture(); d[2][0]["response"] = "[1]"; r = result(d)
        v = r["per_question"][0]["citation"]
        assert (v["precision"], v["recall"], v["f1"]) == original_scores(["text1", "image2"], ["text1"])
        assert abs(v["f1"] - 2/3) < 1e-15
        assert r["exploratory_mean_of_global_modality_f1"]["ratio"] == .5
    case("T03", t03)

    def t04():
        d = fixture(); d[1][0]["gold_quotes"] = ["text1"]; d[2][0]["response"] = "[1] [999]"
        r = result(d); v = r["per_question"][0]
        assert abs(v["citation"]["f1"] - 2/3) < 1e-15 and v["citation"]["fp"] == 1
        assert v["out_of_pool_quotes"] == ["text999"]
        bad = copy.deepcopy(d); bad[1][0]["gold_quotes"] = ["text999"]
        rejected(lambda: result(bad))
    case("T04", t04)

    def t05():
        d = fixture(["synthetic:empty", "synthetic:no_cites", "synthetic:failure"])
        d[2][0]["response"] = ""; d[2][1]["response"] = "fictional answer without citations"
        d[2][2].update({"generation_status": "failed", "generation_error": "ARTIFICIAL_FAILURE", "response": "[1] (image2)"})
        r = result(d)
        assert r["fixed_denominator"] == 3 and r["explicit_generation_failures"] == 1
        assert r["code_compatible_overall_union_macro_f1"]["ratio"] == 0
        assert r["per_question"][2]["response_raw"] == "[1] (image2)" and r["per_question"][2]["response_processed"] == " "
        for value in [None, False, 0, [], {}]:
            assert adapter.process_response(value)[:2] == (" ", " ")
        bad = fixture(); bad[2][0]["truncated"] = "false"
        rejected(lambda: result(bad))
    case("T05", t05)

    def t06():
        d = fixture(); d[1][0]["gold_quotes"] = []; d[2][0]["response"] = ""
        assert result(d)["code_compatible_overall_union_macro_f1"]["ratio"] == 0
        assert original_scores([], []) == (0, 0, 0)
    case("T06", t06)

    def t07():
        for which in [1, 2, 3]:
            d = fixture(["synthetic:a", "synthetic:b"])
            short = copy.deepcopy(d); short[which].pop(); rejected(lambda: result(short))
            long = copy.deepcopy(d); long[which].append(copy.deepcopy(long[which][0])); rejected(lambda: result(long))
            duplicate = copy.deepcopy(d); duplicate[which][1]["q_id"] = "synthetic:a"; rejected(lambda: result(duplicate))
            unknown = copy.deepcopy(d); unknown[which][1]["q_id"] = "synthetic:unknown"; rejected(lambda: result(unknown))
        with tempfile.TemporaryDirectory(prefix="mmdocrag-synthetic-only-") as tmp:
            p = Path(tmp); d = fixture(); d[2].clear()
            for key, value in zip(["manifest", "gold", "predictions", "pools"], d):
                (p/(key+".json")).write_text(json.dumps(value), encoding="utf-8")
            command = [sys.executable, "-B", str(Path(adapter.__file__)), "--output", str(p/"receipt.json")]
            for key in ["manifest", "gold", "predictions", "pools"]:
                command += ["--"+key, str(p/(key+".json"))]
            cp = subprocess.run(command, capture_output=True, text=True)
            receipt = json.loads((p/"receipt.json").read_text())
            assert cp.returncode == 2 and receipt["status"] == "scoring_not_ready" and receipt["scores"] is None
            assert receipt["judge"]["status"] == "not_evaluated"
        rejected(lambda: json.loads('{"q_id":"synthetic:a","q_id":"synthetic:b"}', object_pairs_hook=adapter.no_duplicate_keys))
    case("T07", t07)

    def t08():
        d = fixture(["synthetic:a", "synthetic:b"]); d[2].reverse(); d[3].reverse()
        r = result(d)
        assert r["alignment"]["predictions"]["reordered"]
        assert r["alignment"]["pools"]["reordered"]
        assert [x["q_id"] for x in r["per_question"]] == d[0]["qids"]
    case("T08", t08)

    def t09():
        d = fixture(); d[2][0]["q_id"] = 1; rejected(lambda: result(d))
        d = fixture(); d[0]["qids"] = [True]; d[0]["qid_type"] = "int"; rejected(lambda: result(d))
        d = fixture(); d[0]["qid_type"] = "int"; d[0]["qids"] = [1]
        for rows in d[1:]: rows[0]["q_id"] = 1
        assert result(d)["alignment"]["gold"]["aligned_qid_order"] == [1]
    case("T09", t09)

    def t10():
        text = "[1,2] [1-2] (Image2) (image2) [01] [01] (image02)"
        assert adapter.extract_citations(text) == extract(text) == (["text01"], ["image2", "image02"], ["text01", "image2", "image02"])
    case("T10", t10)

    def t11():
        samples = ["a</think>\n\nb</think>\n\nc", "a seconds\n\nb seconds\n\nc", "a</think>\nb", "a Seconds\n\nb", "x seconds\n\ny</think>\n\nz"]
        for raw in samples:
            expected = raw if raw else " "
            if "</think>\n\n" in expected: expected = expected.split("</think>\n\n")[1]
            elif " seconds\n\n" in expected: expected = expected.split(" seconds\n\n")[1]
            assert adapter.process_response(raw)[1] == expected
        assert adapter.process_response(samples[0])[1] == "b"
    case("T11", t11)

    def t12():
        d = fixture(["synthetic:long", "synthetic:short"])
        d[1][0]["gold_quotes"] = ["text"+str(x) for x in range(1, 10)]
        d[3][0]["quote_ids"] = list(d[1][0]["gold_quotes"])
        d[1][1]["gold_quotes"] = ["text1"]
        d[2][0]["response"] = "[1]"; d[2][1]["response"] = "[1]"
        r = result(d)
        assert abs(r["code_compatible_overall_union_macro_f1"]["ratio"] - .6) < 1e-15
        assert abs(r["code_compatible_modality_global"]["text"]["f1"] - 1/3) < 1e-15
        assert r["fixed_denominator"] == 2
    case("T12", t12)

    def t13():
        for variant in ["all_missing", "partial", "nonnumeric", "negative", "bool"]:
            d = fixture(["synthetic:a", "synthetic:b"])
            if variant == "all_missing":
                for row in d[2]: row.pop("in_tok"); row.pop("out_tok")
            elif variant == "partial": d[2][1].pop("out_tok")
            elif variant == "nonnumeric": d[2][1]["in_tok"] = "12"
            elif variant == "negative": d[2][1]["in_tok"] = -1
            else: d[2][1]["in_tok"] = True
            r = result(d)["tokens"]
            assert r["fixed_denominator"] == 2 and r["mean_input_tokens"] is None and not r["subset_mean_reported"]
        d = fixture(); r = result(d)["tokens"]
        assert r["mean_input_tokens"] == 12 and r["mean_output_tokens"] == 4
    case("T13", t13)

    def t14():
        m = fixture()[0]; q = m["qids"][0]
        valid = [{"q_id": q, "response": dict(zip(adapter.JUDGE_DIMENSIONS, [1, 2, 3, 4, 5]))}]
        assert adapter.validate_judge_rows(valid, m)["status"] == "validated_only_not_evaluated"
        cases = [[], valid+valid, [{"q_id": "synthetic:unknown", "response": valid[0]["response"]}], [{"q_id": q, "response": {}}]]
        for value in [6, -1, float("nan"), float("inf"), "5", True]:
            bad = copy.deepcopy(valid); bad[0]["response"]["Fluency"] = value; cases.append(bad)
        for rows in cases: rejected(lambda: adapter.validate_judge_rows(rows, m))
        assert result(fixture())["judge"]["status"] == "not_evaluated"
    case("T14", t14)

    lexical = adapter.LexicalMetrics()
    lexical_checks = []
    for name, function, upstream_name in [("bleu", lexical.bleu, "calculate_bleu"), ("rougeL", lexical.rouge, "calculate_rouge")]:
        if function is None:
            lexical_checks.append({"metric": name, "status": "not_verified", "reason": lexical.unavailable.get(name)})
            continue
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == upstream_name]
        env = {}
        if name == "bleu":
            from nltk.tokenize import word_tokenize
            from nltk.translate.bleu_score import sentence_bleu
            env.update(word_tokenize=word_tokenize, sentence_bleu=sentence_bleu)
        else:
            from rouge_score import rouge_scorer
            env["rouge_scorer"] = rouge_scorer
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "selected_lexical_function", "exec"), env)
        samples = [("fictional comet crosses four violet moons", "fictional comet crosses four violet moons"), ("a", "a"), ("", ""), ("cats running [1] (image2)", "cat run [1] (image2)")]
        for reference, candidate in samples:
            expected = env[upstream_name](reference, candidate)
            if name == "rougeL": expected = expected["rougeL"].fmeasure
            assert abs(function(reference, candidate) - expected) < 1e-15
        lexical_checks.append({"metric": name, "status": "passed", "examples": len(samples)})
    results.append({"id": "T15", "status": "passed" if all(x["status"] == "passed" for x in lexical_checks) else "not_fully_verified", "components": lexical_checks})
    return {"scorer_id": adapter.SCORER_ID, "scorer_sha256": hashlib.sha256(Path(adapter.__file__).read_bytes()).hexdigest(),
            "environment": {"platform": sys.platform, "python": sys.version.split()[0]},
            "source_sha256": hashlib.sha256(raw).hexdigest(), "source_commit": adapter.UPSTREAM_COMMIT,
            "synthetic_only": True, "cases": results,
            "passed_cases": sum(x["status"] == "passed" for x in results),
            "not_fully_verified_cases": [x["id"] for x in results if x["status"] != "passed"],
            "dependencies": lexical.dependencies, "upstream_module_imported": False,
            "selected_pure_function_AST_executed": True, "upstream_top_level_executed": False,
            "download_or_judge_called": False, "research_QA_read": False,
            "runtime_v1_10_1_changed_or_rerun": False,
            "status": "synthetic_checks_passed_with_explicit_lexical_gaps" if any(x["status"] != "passed" for x in results) else "synthetic_checks_passed"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source_cache)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps({k: result[k] for k in ["status", "passed_cases", "not_fully_verified_cases", "dependencies"]}, ensure_ascii=False))
