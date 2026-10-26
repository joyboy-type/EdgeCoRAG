#!/usr/bin/env python3
"""S3 + Qwen3-VL-8B 补跑（预注册见 PREREGISTRATION_20261026_completion.md §2）。

约束（不可协商）：
  - bf16、quantization=none、greedy、max_new_tokens=64、原生 EOS；
  - 不改 prompt、不改题单、不重排图、不限 max_pixels、不量化；
  - OOM 立即停该模型并保留 partial；失败率 >5% 停。

输出列与既有四模型 S3 csv 完全一致：raw_id,qid,choice,gold,correct,status
"""
import argparse
import csv
import hashlib
import json
import re
import time
from pathlib import Path

import torch

MODEL = "Qwen/Qwen3-VL-8B-Instruct"
REVISION = "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
SPLITS = ["dev", "internal_holdout", "frozen_test"]
SPLIT_OUT = {"dev": "dev", "internal_holdout": "holdout", "frozen_test": "frozen"}
DEFAULT_MEDIA = "/root/autodl-tmp/EdgeCoRAG/bound-v1.10.0/integrated"
MAX_NEW_TOKENS = 64


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def parse_choice(text):
    m = re.search(r"\b([ABCD])\b", text)
    return m.group(1) if m else None


def find_weights(repo, revision):
    dirname = "models--" + repo.replace("/", "--")
    for root in ["/root/autodl-tmp/EdgeCoRAG/cache/huggingface/hub",
                 "/root/autodl-tmp/EdgeCoRAG/cache/huggingface",
                 str(Path.home() / "cache/huggingface/hub")]:
        base = Path(root) / dirname
        if not base.is_dir():
            continue
        snap = base / "snapshots" / revision
        if snap.is_dir() and list(snap.glob("*.safetensors")):
            return str(snap)
        if list(base.glob("*.safetensors")):
            return str(base)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--media", default=DEFAULT_MEDIA)
    ap.add_argument("--out", default="/root/autodl-tmp/run_20261026/s3")
    ap.add_argument("--weights", default="")
    ap.add_argument("--fail-rate-stop", type=float, default=0.05)
    args = ap.parse_args()

    wdir = args.weights or find_weights(MODEL, REVISION)
    if not wdir:
        raise SystemExit(f"权重未找到：{MODEL} @ {REVISION}；先跑 env_check.py")
    media_root_base = Path(args.media)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    t0 = time.time()
    processor = AutoProcessor.from_pretrained(wdir, local_files_only=True, trust_remote_code=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        wdir, local_files_only=True, trust_remote_code=True,
        dtype=torch.bfloat16, attn_implementation="sdpa").to("cuda").eval()
    torch.cuda.synchronize()
    load_seconds = time.time() - t0
    props = torch.cuda.get_device_properties(0)

    runtime = {
        "model": MODEL, "revision": REVISION, "dtype": "bfloat16", "quantization": "none",
        "attn_implementation": "sdpa", "max_new_tokens": MAX_NEW_TOKENS, "do_sample": False,
        "load_seconds": round(load_seconds, 3),
        "gpu_name": torch.cuda.get_device_name(0),
        "gpu_total_gib": round(props.total_memory / 1024**3, 3),
        "compute_capability": list(torch.cuda.get_device_capability(0)),
        "cuda_runtime": torch.version.cuda, "torch": torch.__version__,
        "matmul_allow_tf32": False, "cudnn_allow_tf32": False,
    }
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False

    attempted = 0
    failed = 0
    receipts = []
    stopped_reason = None

    for split in SPLITS:
        s3dir = media_root_base / split / "s3"
        inp_path = s3dir / "inputs" / "S3-pure.json"
        gold_path = s3dir / "scoring" / "answers.json"
        media_root = s3dir / "media"
        if not inp_path.exists() or not gold_path.exists():
            print(f"[{split}] 缺输入或金标，跳过：{inp_path} / {gold_path}", flush=True)
            continue

        items = json.loads(inp_path.read_text(encoding="utf-8"))
        gold_list = json.loads(gold_path.read_text(encoding="utf-8"))
        gold = {str(g["raw_id"]): str(g["answer_choice"]).strip() for g in gold_list}

        rows = []
        for it in items:
            raw_id = str(it["raw_id"])
            g = gold.get(raw_id)
            img_paths = [media_root / o["path"] for o in it["image_order"]]
            missing = [str(p) for p in img_paths if not p.exists()]
            if missing:
                rows.append(dict(raw_id=raw_id, qid=it["qid"], choice=None, gold=g,
                                 correct=None, status=f"missing_images:{len(missing)}"))
                continue
            try:
                from PIL import Image
                imgs = [Image.open(p).convert("RGB") for p in img_paths]
                text = it["model_request"]["messages"][0]["content"][-1]["text"]
                msgs = [{"role": "user", "content": [
                    *[{"type": "image"} for _ in imgs], {"type": "text", "text": text}]}]
                prompt = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
                inputs = processor(text=[prompt], images=[imgs], return_tensors="pt").to("cuda")
                attempted += 1
                with torch.no_grad():
                    oids = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
                gen = oids[0][inputs["input_ids"].shape[1]:]
                resp = processor.decode(gen, skip_special_tokens=True).strip()
                choice = parse_choice(resp)
                correct = (choice == g) if (choice and g) else None
                rows.append(dict(raw_id=raw_id, qid=it["qid"], choice=choice, gold=g,
                                 correct=correct, status="ok"))
            except torch.cuda.OutOfMemoryError as e:
                failed += 1
                rows.append(dict(raw_id=raw_id, qid=it["qid"], choice=None, gold=g,
                                 correct=None, status="OOM"))
                stopped_reason = f"OOM at {split}/{raw_id}: {str(e)[:200]}"
                print(f"[STOP] OOM at {split}/{raw_id}", flush=True)
                break
            except Exception as e:  # noqa: BLE001
                failed += 1
                rows.append(dict(raw_id=raw_id, qid=it["qid"], choice=None, gold=g,
                                 correct=None, status=f"error:{type(e).__name__}"))
                continue

        n = len(rows)
        nc = sum(1 for r in rows if r["correct"] is True)
        csv_p = out / f"s3_qwen3vl_8b_{SPLIT_OUT[split]}.csv"
        with csv_p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["raw_id", "qid", "choice", "gold", "correct", "status"])
            w.writeheader()
            for r in rows:
                w.writerow({k: r[k] for k in ["raw_id", "qid", "choice", "gold", "correct", "status"]})
        receipt = {
            "split": split, "split_out": SPLIT_OUT[split], "n_expected": len(items), "n_rows": n,
            "n_correct": nc, "accuracy": (nc / n) if n else None,
            "complete": n == len(items),
            "input_sha256": sha_file(inp_path), "gold_sha256": sha_file(gold_path),
            "csv_sha256": sha_file(csv_p),
            "disclosure": "AI 图像辅助、label-aware、非人工盲审",
            "note": "子集描述；不产生跨尺度鲁棒性结论",
        }
        receipts.append(receipt)
        print(f"[{split}] n={n}/{len(items)} correct={nc} acc={receipt['accuracy']}", flush=True)

        if stopped_reason:
            break
        if attempted and failed / attempted > args.fail_rate_stop:
            stopped_reason = f"failure_rate {failed}/{attempted} > {args.fail_rate_stop}"
            print(f"[STOP] {stopped_reason}", flush=True)
            break

    summary = {
        "schema": "s3_qwen3vl_8b_20261026/v1",
        "runtime": runtime,
        "split_receipts": receipts,
        "attempted": attempted, "failed": failed,
        "failure_rate": (failed / attempted) if attempted else None,
        "stopped_reason": stopped_reason,
        "preregistration": "PREREGISTRATION_20261026_completion.md §2",
    }
    (out / "receipt_s3_qwen3vl_8b.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"完成：attempted={attempted} failed={failed} stopped={stopped_reason}", flush=True)
    return 0 if all(r["complete"] for r in receipts) and receipts else 4


if __name__ == "__main__":
    raise SystemExit(main())
