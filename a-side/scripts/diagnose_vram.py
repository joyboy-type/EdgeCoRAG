"""查明 E4B 在 8 GB 显存上超限的原因,并测试可用的降显存手段。

背景(实测):
    E2B 4bit -> 6.28 GiB 已分配, 生成 2 步 1.0s
    E4B 4bit -> 8.68 GiB 已分配(峰值 8.98), 生成 2 步 25.2s  <-- 超出 8.0 GiB 总额

E2B(5.12B) 与 E4B(8.00B) 的 4bit 权重理论差约 1.4 GiB,但实测差 2.4 GiB。
本脚本把显存占用拆开,量化各组件,并测试降显存手段:
    1. 各模块参数量分解(找出真正吃显存的部分)
    2. 图像分辨率的实际视觉 token 数(视觉塔是主要激活来源)
    3. 不同图像尺寸下的峰值显存
    4. KV cache 与 max_new_tokens 的关系

用法:
    python scripts/diagnose_vram.py --model google/gemma-4-E4B-it
    python scripts/diagnose_vram.py --model google/gemma-4-E4B-it --sweep-image-size
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def setup_env() -> None:
    """缓存位置由 scripts/project_config.py 决定(工作区之外)。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    import project_config as cfg
    cfg.apply_env()


def free() -> None:
    import torch

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()


def vram() -> dict:
    import torch

    if not torch.cuda.is_available():
        return {}
    return {
        "allocated_GiB": round(torch.cuda.memory_allocated() / 1024 ** 3, 3),
        "reserved_GiB": round(torch.cuda.memory_reserved() / 1024 ** 3, 3),
        "peak_allocated_GiB": round(torch.cuda.max_memory_allocated() / 1024 ** 3, 3),
        "peak_reserved_GiB": round(torch.cuda.max_memory_reserved() / 1024 ** 3, 3),
    }


def load(model_id: str, four_bit: bool = True):
    import torch
    from transformers import AutoProcessor, BitsAndBytesConfig, Gemma4ForConditionalGeneration

    kwargs: dict = {}
    if four_bit:
        kwargs["device_map"] = {"": 0}
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
    else:
        kwargs["device_map"] = "auto"
        kwargs["torch_dtype"] = torch.bfloat16
    model = Gemma4ForConditionalGeneration.from_pretrained(model_id, **kwargs).eval()
    proc = AutoProcessor.from_pretrained(model_id)
    return model, proc


def breakdown(model) -> list[tuple[str, float, str]]:
    """按顶层模块统计参数量与 dtype。"""
    rows = []
    for name, child in model.named_children():
        n = sum(p.numel() for p in child.parameters())
        dtypes = {str(p.dtype) for p in child.parameters()}
        rows.append((name, n / 1e9, ",".join(sorted(dtypes))))
    rows.sort(key=lambda r: -r[1])
    return rows


def tokenizer_len(proc) -> int:
    tok = getattr(proc, "tokenizer", proc)
    return len(tok)


def run_case(model, proc, image_size: int, n_images: int, max_new_tokens: int) -> dict:
    import torch
    from PIL import Image

    free()
    tok = getattr(proc, "tokenizer", proc)
    img = Image.new("RGB", (image_size, image_size), (180, 90, 40))
    query = "Which image shows a chart with an increasing trend?"
    text = f"Query: {query}\nIs this evidence helpful for answering the query?\nAnswer with True or False."
    content = [{"type": "image", "image": img} for _ in range(n_images)]
    content.append({"type": "text", "text": text})
    messages = [{"role": "user", "content": content}]
    prompt = proc.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
    inputs = proc(text=[prompt], images=[img] * n_images, return_tensors="pt")
    inputs = {k: (v.to(model.device) if hasattr(v, "to") else v) for k, v in inputs.items()}
    n_vis = int(inputs["pixel_values"].shape[1]) if "pixel_values" in inputs else 0
    n_tok = int(inputs["input_ids"].shape[1])

    after_prefill = vram()
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens,
                             do_sample=False, output_scores=True,
                             return_dict_in_generate=True)
    dt = time.time() - t0
    peak = vram()
    gen = tok.decode(out.sequences[0][n_tok:], skip_special_tokens=False)
    return {
        "image_size": image_size, "n_images": n_images,
        "max_new_tokens": max_new_tokens,
        "input_tokens": n_tok, "vision_tokens": n_vis,
        "vision_tokens_per_image": n_vis // max(n_images, 1),
        "prefill_vram": after_prefill, "peak_vram": peak,
        "generate_seconds": round(dt, 2),
        "generated": gen,
    }


def main() -> int:
    setup_env()
    import torch

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="google/gemma-4-E4B-it")
    ap.add_argument("--sweep-image-size", action="store_true")
    ap.add_argument("--four-bit", action="store_true", default=True)
    args = ap.parse_args()

    print(f"模型: {args.model}")
    print(f"显存总额: {torch.cuda.get_device_properties(0).total_memory / 1024 ** 3:.2f} GiB")

    free()
    t0 = time.time()
    model, proc = load(args.model, four_bit=True)
    print(f"\n加载耗时 {time.time() - t0:.1f}s")
    print(f"加载后显存: {vram()}")

    print(f"\n{'=' * 70}\n顶层模块参数量分解\n{'=' * 70}")
    tot = 0.0
    for name, params, dtypes in breakdown(model):
        tot += params
        print(f"  {name:28s} {params:7.3f} B   [{dtypes}]")
    print(f"  {'总计':28s} {tot:7.3f} B")
    print(f"\n  词表大小: {tokenizer_len(proc)}")

    print(f"\n{'=' * 70}\n单图不同尺寸的视觉 token 数(视觉塔是激活值主要来源)\n{'=' * 70}")
    results = []
    sizes = [224, 448, 896] if args.sweep_image_size else [448]
    for sz in sizes:
        try:
            r = run_case(model, proc, image_size=sz, n_images=1, max_new_tokens=4)
            results.append(r)
            print(f"  尺寸 {sz:4d}px -> 视觉 token {r['vision_tokens']:5d} "
                  f"(每图 {r['vision_tokens_per_image']}), 输入 {r['input_tokens']:4d} tok, "
                  f"峰值 allocated={r['peak_vram']['peak_allocated_GiB']:.2f} / "
                  f"reserved={r['peak_vram']['peak_reserved_GiB']:.2f} GiB, "
                  f"生成 {r['generate_seconds']:.1f}s")
        except Exception as exc:  # noqa: BLE001
            print(f"  尺寸 {sz:4d}px -> ✗ {type(exc).__name__}: {str(exc)[:150]}")
            free()

    if args.sweep_image_size:
        print(f"\n{'=' * 70}\n多图输入的影响(路径 A1/A3 需要多张候选图)\n{'=' * 70}")
        for n in (1, 2, 4):
            try:
                r = run_case(model, proc, image_size=448, n_images=n, max_new_tokens=4)
                results.append(r)
                print(f"  {n} 张图 -> 视觉 token {r['vision_tokens']:5d}, "
                      f"输入 {r['input_tokens']:4d} tok, 峰值 "
                      f"reserved={r['peak_vram']['peak_reserved_GiB']:.2f} GiB, "
                      f"生成 {r['generate_seconds']:.1f}s")
            except Exception as exc:  # noqa: BLE001
                print(f"  {n} 张图 -> ✗ {type(exc).__name__}: {str(exc)[:120]}")
                free()

    outdir = ROOT / "outputs" / "gemma4_probe"
    outdir.mkdir(parents=True, exist_ok=True)
    tag = args.model.split("/")[-1]
    (outdir / f"vram_diagnosis_{tag}.json").write_text(json.dumps({
        "model": args.model,
        "gpu_total_GiB": round(torch.cuda.get_device_properties(0).total_memory / 1024 ** 3, 2),
        "vram_after_load": vram(),
        "module_breakdown": [{"module": n, "params_B": round(p, 3), "dtypes": d}
                             for n, p, d in breakdown(model)],
        "cases": results,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {outdir / f'vram_diagnosis_{tag}.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
