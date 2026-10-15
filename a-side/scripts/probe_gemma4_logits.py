"""验证「证据有用性打分」能否移植到 Gemma 4 —— 本项目最大的技术风险点。

背景(任务书第 3 节):
    作者 utility-mrag 的 gemma.py 硬编码 Gemma3ForConditionalGeneration,
    而 Gemma 4 的架构是 Gemma4ForConditionalGeneration(model_type=gemma4,
    pipeline_tag=any-to-any)。核心问题是:
        Gemma 4 能否像论文那样,从辅助二分类提问中取到 "True"/"False" 的末层 logit?

本脚本分两阶段:
    阶段 1 (--stage tokenizer)  秒级,不需要权重: 检查分词器如何编码 True/False
    阶段 2 (--stage model)      需要权重: 真正前向一次,取 logit,验证打分可用

用法:
    python scripts/probe_gemma4_logits.py --stage tokenizer
    python scripts/probe_gemma4_logits.py --stage model --model google/gemma-4-E2B-it
    python scripts/probe_gemma4_logits.py --stage model --load-in-4bit

显存约束(实测): E2B BF16 = 9.54 GiB > 8 GB 显存,故默认 device_map="auto"
会在显存不足时自动把部分层放到 CPU;--load-in-4bit 需要 bitsandbytes。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UTILITY_MRAG = ROOT / "third_party" / "utility-mrag"

# 论文使用的辅助提问(式 5)
AUX_QUESTION = "Is this evidence helpful for answering the query?"


def setup_env() -> None:
    """缓存位置由 scripts/project_config.py 决定(工作区之外)。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    import project_config as cfg
    cfg.apply_env()
    # 让作者的 TrueFalseLogitExtractor 可导入(不做 pip install)
    sys.path.insert(0, str(UTILITY_MRAG))
    sys.path.insert(0, str(UTILITY_MRAG / "utility_mrag"))


def stage_tokenizer(model_id: str) -> int:
    """检查分词器对 True/False 的编码方式。"""
    from transformers import AutoTokenizer

    print(f"[阶段1] 分词器检查: {model_id}")
    t0 = time.time()
    try:
        tok = AutoTokenizer.from_pretrained(model_id)
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ 加载分词器失败: {type(exc).__name__}: {exc}")
        return 1
    print(f"  加载完成 {time.time() - t0:.1f}s, 词表={len(tok)}")

    results = {}
    for s in ("True", "False", " True", " False", "true", "false", "Yes", "No"):
        ids = tok.encode(s, add_special_tokens=False)
        pieces = [tok.decode([i]) for i in ids]
        results[s] = ids
        flag = "单 token ✅" if len(ids) == 1 else f"多 token ⚠️ ({len(ids)} 片)"
        print(f"  {s!r:10s} -> ids={ids}  pieces={pieces}  {flag}")

    # 关键: True / False 是否都能落到单 token
    ok_true = len(results["True"]) == 1 or len(results[" True"]) == 1
    ok_false = len(results["False"]) == 1 or len(results[" False"]) == 1
    print(f"\n  结论: True 可用={ok_true}, False 可用={ok_false}")
    if not (ok_true and ok_false):
        print("  ⚠️ 至少一个不是单 token,作者的 TrueFalseLogitExtractor 会回退到首片段,")
        print("     需在报告中记录该降级(可能影响打分质量)。")

    # 直接用作者的解析器确认它算出什么
    try:
        from utility_mrag.scoring.true_false_logits import TrueFalseLogitExtractor
        ex = TrueFalseLogitExtractor(tok)
        print(f"\n  [作者解析器] positive_token_id={ex.positive_token_id} "
              f"negative_token_id={ex.negative_token_id}")
        warns = ex.warn_if_multi_token()
        if warns:
            for w in warns:
                print(f"  ⚠️ {w}")
        else:
            print("  ✅ 无多 token 降级警告")
    except Exception as exc:  # noqa: BLE001
        print(f"  ! 无法导入作者解析器: {type(exc).__name__}: {exc}")

    out = ROOT / "outputs" / "gemma4_probe" / "tokenizer_check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model_id": model_id,
        "vocab_size": len(tok),
        "encodings": {k: list(v) for k, v in results.items()},
        "true_single_token": bool(ok_true),
        "false_single_token": bool(ok_false),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  -> {out}")
    return 0


def stage_model(model_id: str, load_in_4bit: bool, max_new_tokens: int) -> int:
    """真正加载模型,取一次打分,验证端到端可用。"""
    import torch
    from PIL import Image
    from transformers import AutoProcessor

    print(f"[阶段2] 真实打分验证: {model_id}")
    if not torch.cuda.is_available():
        print("  ⚠️ CUDA 不可用,会在 CPU 上跑,极慢")

    # 1) 处理器
    tok = AutoProcessor.from_pretrained(model_id)

    # 2) 模型: Gemma 4 用 Gemma4ForConditionalGeneration
    import transformers

    print(f"  transformers 版本: {transformers.__version__}")
    model_cls = None
    for name in ("Gemma4ForConditionalGeneration", "AutoModelForImageTextToText",
                 "AutoModelForMultimodalLM"):
        model_cls = getattr(transformers, name, None)
        if model_cls is not None:
            print(f"  使用模型类: {name}")
            break
    if model_cls is None:
        print("  ✗ 找不到可用的 Gemma 4 模型类")
        return 1

    kwargs: dict = {}
    if load_in_4bit:
        try:
            from transformers import BitsAndBytesConfig
            # 4bit 时强制整模型放在 GPU0:量化后 E2B≈2.39 GiB / E4B≈3.72 GiB,可以全驻留。
            # 不用 device_map="auto",否则 accelerate 可能把大部分层 offload 到 CPU
            # (实测 BF16 下出现 cuda:0=19.2% / meta=80.8% 的退化分布)。
            kwargs["device_map"] = {"": 0}
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
            )
            print("  量化: 4bit (nf4, double quant), device_map={'': 0} 全驻显存")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! 无法配置 4bit 量化({exc}),回退 device_map=auto")
            kwargs["device_map"] = "auto"
            kwargs["torch_dtype"] = torch.bfloat16
    else:
        kwargs["device_map"] = "auto"
        kwargs["torch_dtype"] = torch.bfloat16
        print("  精度: bfloat16, device_map=auto(显存不足会自动 offload 到 CPU)")

    t0 = time.time()
    model = model_cls.from_pretrained(model_id, **kwargs).eval()
    print(f"  模型加载完成 {time.time() - t0:.1f}s")
    if torch.cuda.is_available():
        print(f"  显存已分配 {torch.cuda.memory_allocated() / 1024 ** 3:.2f} GiB")
    # 报告模型实际分布
    try:
        dev = {}
        for p in model.parameters():
            dev[str(p.device)] = dev.get(str(p.device), 0) + p.numel()
        total = sum(dev.values())
        print("  参数设备分布: " + ", ".join(
            f"{k}={v / total * 100:.1f}%" for k, v in sorted(dev.items())))
    except Exception:  # noqa: BLE001
        pass

    # 3) 构造一次打分: 合成图 + 辅助提问
    query = "Which image shows a chart with an increasing trend?"
    img = Image.new("RGB", (224, 224), (200, 60, 60))
    text = f"Query: {query}\n{AUX_QUESTION}\nAnswer with True or False."

    messages = [{"role": "user", "content": [
        {"type": "image", "image": img},
        {"type": "text", "text": text},
    ]}]
    prompt = tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
    inputs = tok(text=[prompt], images=[img], return_tensors="pt")
    inputs = {k: (v.to(model.device) if hasattr(v, "to") else v) for k, v in inputs.items()}
    print(f"  输入 shape: " + ", ".join(f"{k}={tuple(v.shape)}" for k, v in inputs.items()
                                        if hasattr(v, 'shape')))

    # 4) 取第一个生成步的 logits (output_scores)
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False,
                             output_scores=True, return_dict_in_generate=True)
    dt = time.time() - t0
    scores = out.scores
    print(f"  生成完成 {dt:.1f}s, 生成 {len(scores)} 步")
    if torch.cuda.is_available():
        print(f"  峰值显存 reserved={torch.cuda.max_memory_reserved() / 1024 ** 3:.2f} GiB, "
              f"allocated={torch.cuda.max_memory_allocated() / 1024 ** 3:.2f} GiB")

    if not scores:
        print("  ✗ 没有 scores,无法取 logit")
        return 1
    first = scores[0]
    print(f"  首步 logits shape: {tuple(first.shape)}")

    # 5) 用作者解析器算打分
    sys.path.insert(0, str(UTILITY_MRAG))
    from utility_mrag.scoring.true_false_logits import TrueFalseLogitExtractor

    tokenizer = getattr(tok, "tokenizer", tok)
    extractor = TrueFalseLogitExtractor(tokenizer)
    for w in extractor.warn_if_multi_token():
        print(f"  ⚠️ {w}")
    res = extractor.compute(first)
    print("\n  === 打分结果(作者 TrueFalseLogitExtractor)===")
    for k, v in res.items():
        print(f"    {k:24s} = {v}")

    # 6) 生成的文本,人工确认模型真的在回答 True/False
    gen = tokenizer.decode(out.sequences[0][inputs["input_ids"].shape[1]:],
                           skip_special_tokens=False)
    print(f"\n  生成文本: {gen!r}")

    ok = res["true_token_id"] is not None and res["score"] is not None
    print(f"\n  {'✅' if ok else '✗'} 打分链路{'可用' if ok else '不可用'}")

    outdir = ROOT / "outputs" / "gemma4_probe"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "logit_probe.json").write_text(json.dumps({
        "model_id": model_id,
        "load_in_4bit": load_in_4bit,
        "prompt": prompt,
        "generated_text": gen,
        "scores_steps": len(scores),
        "first_step_logits_shape": list(first.shape),
        "extractor_result": res,
        "generate_seconds": dt,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {outdir / 'logit_probe.json'}")
    return 0 if ok else 1


def main() -> int:
    setup_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["tokenizer", "model", "both"], default="tokenizer")
    ap.add_argument("--model", default="google/gemma-4-E2B-it")
    ap.add_argument("--load-in-4bit", action="store_true")
    ap.add_argument("--max-new-tokens", type=int, default=4)
    args = ap.parse_args()

    rc = 0
    if args.stage in ("tokenizer", "both"):
        rc |= stage_tokenizer(args.model)
    if args.stage in ("model", "both"):
        rc |= stage_model(args.model, args.load_in_4bit, args.max_new_tokens)
    return rc


if __name__ == "__main__":
    sys.exit(main())
