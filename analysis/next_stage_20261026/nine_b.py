#!/usr/bin/env python3
"""Qwen3.5-9B 补跑：可行性验证 + S0/S1/S2 × 1,033（预注册见 PREREGISTRATION_20261026_completion.md §3）。

关键点（踩过的坑，均已固化）：
  1. model_type=qwen3_5 → Qwen3_5ForConditionalGeneration（transformers 5.19+ 才有该类）；
  2. Qwen3.5 的 processor 不自动透传 tokenizer 的 chat_template → 从 tokenizer_config.json 显式回填；
  3. 必须 enable_thinking=False，否则输出推理段、解析不到 A/B/C/D；
  4. 线性注意力需 flash-linear-attention（Triton JIT）+ causal_conv1d（需 nvcc），否则回退参考实现、单题 >10 分钟。

用法：
  python nine_b.py --mode feasibility          # 只跑 3 题，判单题是否 <=30s
  python nine_b.py --mode full                 # S0/S1/S2 全量 1,033
"""
import argparse
import csv
import hashlib
import json
import re
import time
from pathlib import Path

import torch

MODEL = "Qwen/Qwen3.5-9B"
REVISION = "c202236235762e1c871ad0ccb60c8ee5ba337b9a"
CONDS = ["S0", "S1", "S2"]
DEFAULT_MEDIA = "/root/autodl-tmp/EdgeCoRAG/bound-v1.10.0/integrated/frozen_test/main"
MAX_NEW_TOKENS = 64
FEASIBILITY_N = 3
FEASIBILITY_SECONDS_PER_ITEM = 30.0


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_choice(text):
    m = re.search(r"\b([ABCD])\b", text)
    return m.group(1) if m else None


def find_weights():
    dirname = "models--" + MODEL.replace("/", "--")
    for root in ["/root/autodl-tmp/EdgeCoRAG/cache/huggingface/hub",
                 "/root/autodl-tmp/EdgeCoRAG/cache/huggingface",
                 str(Path.home() / "cache/huggingface/hub")]:
        base = Path(root) / dirname
        if not base.is_dir():
            continue
        snap = base / "snapshots" / REVISION
        if snap.is_dir() and list(snap.glob("*.safetensors")):
            return str(snap)
        if list(base.glob("*.safetensors")):
            return str(base)
    return None


def load_stack(wdir):
    from transformers import AutoProcessor
    from transformers import Qwen3_5ForConditionalGeneration as C

    processor = AutoProcessor.from_pretrained(wdir, local_files_only=True, trust_remote_code=True)
    chat_template_sha = None
    if getattr(processor, "chat_template", None) is None:
        cfg = Path(wdir) / "tokenizer_config.json"
        ct = json.loads(cfg.read_text(encoding="utf-8")).get("chat_template")
        if not ct:
            raise SystemExit("tokenizer_config.json 中没有 chat_template，无法渲染")
        processor.chat_template = ct
        if hasattr(processor, "tokenizer"):
            processor.tokenizer.chat_template = ct
    chat_template_sha = hashlib.sha256(
        (getattr(processor, "chat_template", "") or "").encode("utf-8")).hexdigest()

    t0 = time.time()
    model = C.from_pretrained(wdir, local_files_only=True, trust_remote_code=True,
                              dtype=torch.bfloat16, attn_implementation="sdpa").to("cuda").eval()
    torch.cuda.synchronize()
    return processor, model, chat_template_sha, time.time() - t0


def run_one(processor, model, it, media_root, device="cuda"):
    from PIL import Image
    img_paths = [media_root / o["path"] for o in it["image_order"]]
    missing = [str(p) for p in img_paths if not p.exists()]
    if missing:
        return None, f"missing_images:{len(missing)}", 0.0
    imgs = [Image.open(p).convert("RGB") for p in img_paths]
    text = it["model_request"]["messages"][0]["content"][-1]["text"]
    msgs = [{"role": "user", "content": [
        *[{"type": "image"} for _ in imgs], {"type": "text", "text": text}]}]
    prompt = processor.apply_chat_template(
        msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    inputs = processor(text=[prompt], images=[imgs], return_tensors="pt").to(device)
    t0 = time.time()
    with torch.no_grad():
        oids = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
    if device == "cuda":
        torch.cuda.synchronize()
    dt = time.time() - t0
    gen = oids[0][inputs["input_ids"].shape[1]:]
    resp = processor.decode(gen, skip_special_tokens=True).strip()
    return resp, "ok", dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["feasibility", "full"], required=True)
    ap.add_argument("--media", default=DEFAULT_MEDIA)
    ap.add_argument("--out", default="/root/autodl-tmp/run_20261026/9b")
    ap.add_argument("--weights", default="")
    ap.add_argument("--fail-rate-stop", type=float, default=0.05)
    args = ap.parse_args()

    wdir = args.weights or find_weights()
    if not wdir:
        raise SystemExit(f"权重未找到：{MODEL} @ {REVISION}；先跑 env_check.py")
    media = Path(args.media)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    import fla  # noqa: F401  强制要求：缺 fla 直接失败，不静默走参考实现
    fla_version = getattr(fla, "__version__", None)
    try:
        import causal_conv1d
        cc_version = getattr(causal_conv1d, "__version__", None)
    except Exception:
        cc_version = None

    processor, model, ct_sha, load_seconds = load_stack(wdir)
    props = torch.cuda.get_device_properties(0)
    runtime = {
        "model": MODEL, "revision": REVISION, "dtype": "bfloat16", "quantization": "none",
        "attn_implementation": "sdpa", "max_new_tokens": MAX_NEW_TOKENS, "do_sample": False,
        "enable_thinking": False, "load_seconds": round(load_seconds, 3),
        "gpu_name": torch.cuda.get_device_name(0),
        "gpu_total_gib": round(props.total_memory / 1024**3, 3),
        "compute_capability": list(torch.cuda.get_device_capability(0)),
        "cuda_runtime": torch.version.cuda, "torch": torch.__version__,
        "flash_linear_attention": fla_version, "causal_conv1d": cc_version,
        "chat_template_sha256": ct_sha,
    }

    s0 = json.loads((media / "inputs" / "S0.json").read_text(encoding="utf-8"))
    gold_list = json.loads((media / "scoring" / "answers.json").read_text(encoding="utf-8"))
    gold = {str(g["raw_id"]): str(g["answer_choice"]).strip() for g in gold_list}
    media_root = media / "media"

    # ---------- 可行性验证 ----------
    if args.mode == "feasibility":
        times, results = [], []
        for it in s0[:FEASIBILITY_N]:
            try:
                resp, status, dt = run_one(processor, model, it, media_root)
            except torch.cuda.OutOfMemoryError as e:
                results.append({"qid": it["qid"], "status": "OOM", "error": str(e)[:200]})
                break
            times.append(dt)
            results.append({"qid": it["qid"], "status": status, "seconds": round(dt, 3),
                            "choice": parse_choice(resp) if resp else None,
                            "gold": gold.get(str(it["raw_id"]))})
        mean_s = (sum(times) / len(times)) if times else None
        passed = bool(mean_s is not None and mean_s <= FEASIBILITY_SECONDS_PER_ITEM)
        receipt = {
            "schema": "nine_b_feasibility_20261026/v1", "runtime": runtime,
            "n": len(times), "seconds_each": [round(t, 3) for t in times],
            "mean_seconds": round(mean_s, 3) if mean_s else None,
            "threshold_seconds": FEASIBILITY_SECONDS_PER_ITEM,
            "passed": passed, "results": results,
            "preregistration": "PREREGISTRATION_20261026_completion.md §3.3",
        }
        (out / "receipt_feasibility.json").write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({k: receipt[k] for k in
                          ["n", "seconds_each", "mean_seconds", "threshold_seconds", "passed"]},
                         ensure_ascii=False, indent=2))
        return 0 if passed else 5

    # ---------- 全量 ----------
    attempted = failed = 0
    receipts = []
    stopped = None
    for cond in CONDS:
        inp = media / "inputs" / f"{cond}.json"
        items = json.loads(inp.read_text(encoding="utf-8"))
        rows = []
        for it in items:
            raw_id = str(it["raw_id"])
            g = gold.get(raw_id)
            try:
                resp, status, dt = run_one(processor, model, it, media_root)
                attempted += 1
                choice = parse_choice(resp) if resp else None
                correct = (choice == g) if (choice and g) else None
                rows.append(dict(raw_id=raw_id, qid=it["qid"], choice=choice, gold=g,
                                 correct=correct, status=status, seconds=round(dt, 3)))
            except torch.cuda.OutOfMemoryError as e:
                failed += 1
                rows.append(dict(raw_id=raw_id, qid=it["qid"], choice=None, gold=g,
                                 correct=None, status="OOM", seconds=None))
                stopped = f"OOM at {cond}/{raw_id}: {str(e)[:200]}"
                print(f"[STOP] {stopped}", flush=True)
                break
            except Exception as e:  # noqa: BLE001
                failed += 1
                rows.append(dict(raw_id=raw_id, qid=it["qid"], choice=None, gold=g,
                                 correct=None, status=f"error:{type(e).__name__}", seconds=None))

        n = len(rows)
        nc = sum(1 for r in rows if r["correct"] is True)
        csv_p = out / f"s0s1s2_qwen35_9b_{cond}.csv"
        with csv_p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["raw_id", "qid", "choice", "gold", "correct", "status"])
            w.writeheader()
            for r in rows:
                w.writerow({k: r[k] for k in ["raw_id", "qid", "choice", "gold", "correct", "status"]})
        secs = [r["seconds"] for r in rows if r.get("seconds")]
        receipts.append({
            "condition": cond, "n_expected": len(items), "n_rows": n, "n_correct": nc,
            "accuracy": (nc / n) if n else None, "complete": n == len(items),
            "seconds_mean": round(sum(secs) / len(secs), 3) if secs else None,
            "input_sha256": sha_file(inp), "csv_sha256": sha_file(csv_p),
            "note": "Qwen3.5 与 Qwen3-VL 属不同模型家族；不可作纯规模趋势",
        })
        print(f"[{cond}] n={n}/{len(items)} correct={nc} acc={receipts[-1]['accuracy']}", flush=True)
        if stopped:
            break
        if attempted and failed / attempted > args.fail_rate_stop:
            stopped = f"failure_rate {failed}/{attempted} > {args.fail_rate_stop}"
            print(f"[STOP] {stopped}", flush=True)
            break

    summary = {
        "schema": "qwen35_9b_20261026/v1", "runtime": runtime,
        "condition_receipts": receipts, "attempted": attempted, "failed": failed,
        "failure_rate": (failed / attempted) if attempted else None,
        "stopped_reason": stopped,
        "preregistration": "PREREGISTRATION_20261026_completion.md §3",
    }
    (out / "receipt_qwen35_9b.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"完成：attempted={attempted} failed={failed} stopped={stopped}", flush=True)
    return 0 if all(r["complete"] for r in receipts) and len(receipts) == 3 else 4


if __name__ == "__main__":
    raise SystemExit(main())
