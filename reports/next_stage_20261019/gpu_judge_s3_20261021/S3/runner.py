#!/usr/bin/env python3
"""Qwen S3 v3：auto class + enable_thinking=False（qwen35）+ 8bit 可选。
用 qwen35 env（transformers 5.19，含 Qwen3_5 与 Qwen3_VL 两 class）。"""
import argparse, csv, hashlib, json, re, time
from pathlib import Path
import torch
from transformers import AutoProcessor, AutoConfig

MEDIA = "/root/autodl-tmp/EdgeCoRAG/bound-v1.10.0/integrated"
GOLD = "/root/autodl-tmp/edgecorag-a/s3/s3_gold.json"
SPLITS = ["dev", "internal_holdout", "frozen_test"]
MODELS = [
    ("qwen3vl_4b", "/root/autodl-tmp/EdgeCoRAG/cache/huggingface/hub/models--Qwen--Qwen3-VL-4B-Instruct/snapshots/ebb281ec70b05090aa6165b016eac8ec08e71b17", "qwen3vl"),
    ("qwen3vl_8b", "/root/autodl-tmp/EdgeCoRAG/cache/huggingface/hub/models--Qwen--Qwen3-VL-8B-Instruct/snapshots/0c351dd01ed87e9c1b53cbc748cba10e6187ff3b", "qwen3vl"),
    ("qwen35_4b", "/root/autodl-tmp/EdgeCoRAG/cache/huggingface/hub/models--Qwen--Qwen3.5-4B/snapshots/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a", "qwen35"),
]


def sha_file(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def parse_choice(t):
    m = re.search(r"\b([ABCD])\b", t)
    return m.group(1) if m else None


def load_model(wdir, device, load8bit):
    cfg = AutoConfig.from_pretrained(wdir, local_files_only=True, trust_remote_code=True)
    mt = cfg.model_type
    C = None
    if mt == "qwen3_5":
        from transformers import Qwen3_5ForConditionalGeneration
        C = Qwen3_5ForConditionalGeneration
    elif mt == "qwen3_vl":
        from transformers import Qwen3VLForConditionalGeneration
        C = Qwen3VLForConditionalGeneration
    kw = dict(local_files_only=True, trust_remote_code=True)
    if load8bit:
        from transformers import BitsAndBytesConfig
        kw["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
    else:
        kw["dtype"] = torch.bfloat16
    m = C.from_pretrained(wdir, **kw)
    return m.to(device) if not load8bit else m, mt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/root/autodl-tmp/edgecorag-a/s3")
    ap.add_argument("--models", default="qwen3vl_4b,qwen3vl_8b,qwen35_4b")
    ap.add_argument("--load8bit", action="store_true")
    ap.add_argument("--load8bit-models", default="")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    gold = json.loads(Path(GOLD).read_text(encoding="utf-8"))
    device = "cuda"
    only8 = set(args.load8bit_models.split(",")) if args.load8bit_models else set()

    for key, wdir, fam in MODELS:
        if key not in args.models.split(","):
            continue
        lb = args.load8bit or key in only8
        print(f"=== {key} (8bit={lb}) ===", flush=True)
        try:
            processor = AutoProcessor.from_pretrained(wdir, local_files_only=True, trust_remote_code=True)
            model, mt = load_model(wdir, device, lb)
            model.eval()
        except Exception as e:
            print(f"  LOAD FAIL {key}: {e}", flush=True); continue
        for split in SPLITS:
            inp = Path(MEDIA) / split / "s3" / "inputs" / "S3-pure.json"
            if not inp.exists(): continue
            items = json.loads(inp.read_text(encoding="utf-8"))
            media_root = Path(MEDIA) / split / "s3" / "media"
            rows = []; t0 = time.time()
            for it in items:
                raw_id = str(it["raw_id"]); g = gold.get(raw_id)
                img_paths = [media_root / o["path"] for o in it["image_order"]]
                if any(not Path(p).exists() for p in img_paths):
                    rows.append(dict(raw_id=raw_id, qid=it["qid"], choice=None, gold=g["answer"] if g else None, correct=None, status="missing_images")); continue
                from PIL import Image
                imgs = [Image.open(p).convert("RGB") for p in img_paths]
                text = it["model_request"]["messages"][0]["content"][-1]["text"]
                msgs = [{"role": "user", "content": [*[{"type": "image"} for _ in imgs], {"type": "text", "text": text}]}]
                tkw = dict(tokenize=False, add_generation_prompt=True)
                if mt == "qwen3_5":
                    tkw["enable_thinking"] = False
                prompt = processor.apply_chat_template(msgs, **tkw)
                inputs = processor(text=[prompt], images=[imgs], return_tensors="pt").to(device)
                with torch.no_grad():
                    oids = model.generate(**inputs, max_new_tokens=64, do_sample=False)
                gen = oids[0][inputs["input_ids"].shape[1]:]
                resp = processor.decode(gen, skip_special_tokens=True).strip()
                choice = parse_choice(resp)
                correct = (choice == g["answer"]) if (choice and g) else None
                rows.append(dict(raw_id=raw_id, qid=it["qid"], choice=choice, gold=g["answer"] if g else None, correct=correct, status="ok", raw=resp))
            n = len(rows); nc = sum(1 for r in rows if r["correct"] is True); acc = nc / n if n else None
            csv_p = out / f"S3_qwen_{key}_{split}.csv"
            with csv_p.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["raw_id", "qid", "choice", "gold", "correct", "status"])
                w.writeheader()
                for r in rows: w.writerow({k: r[k] for k in ["raw_id", "qid", "choice", "gold", "correct", "status"]})
            receipt = dict(model=key, split=split, n=n, n_correct=nc, accuracy=acc, load8bit=lb,
                           review_method="image_model_assisted", disclosure="AI 图像辅助、label-aware、非人工盲审",
                           csv_sha256=sha_file(csv_p), elapsed_seconds=time.time() - t0)
            (out / f"receipt_{key}_{split}.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"  {key}/{split}: n={n} correct={nc} acc={acc}", flush=True)
        del model; torch.cuda.empty_cache()
    print("DONE s3 v3", flush=True)


if __name__ == "__main__":
    main()
