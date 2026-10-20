"""把 HuggingFace safetensors 权重整体转换为 fp16（端侧量化的第一步）。

HMQuantool 只接受 **fp16 的 ONNX/模型** 作为量化输入，所以流程固定为
fp32 → （可选融合）→ fp16 → 导出 fp16 ONNX → HMQuantool 量化。

用法：
  python scripts/to_fp16.py --model weights/X-VLA-WidowX-fused --out weights/X-VLA-WidowX-fp16 --dry-run
  python scripts/to_fp16.py --model weights/X-VLA-WidowX-fused --out weights/X-VLA-WidowX-fp16

内存提示：加载 fp32 权重 + 写出 fp16，峰值约 1.5 倍源文件大小，建议 ≥8 GB 可用内存。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

WEIGHT_FILE = "model.safetensors"
COPY_SUFFIXES: tuple[str, ...] = (".py", ".json", ".txt", ".model", ".md")
KEEP_FP32_HINTS: tuple[str, ...] = ("norm", "layernorm", "pos_emb", "soft_prompt")


def read_shapes(weight_path: Path) -> dict[str, tuple[int, ...]]:
    """只读 header 获取键与形状（不加载张量）。"""
    from safetensors import safe_open

    with safe_open(str(weight_path), framework="pt") as handle:
        return {key: tuple(handle.get_slice(key).get_shape()) for key in handle.keys()}


def read_dtypes(weight_path: Path) -> dict[str, str]:
    """只读 header 获取每个张量的 dtype 字符串。"""
    from safetensors import safe_open

    with safe_open(str(weight_path), framework="pt") as handle:
        return {key: str(handle.get_slice(key).get_dtype()) for key in handle.keys()}


def load_weights(weight_path: Path) -> dict:
    from safetensors.torch import load_file

    return load_file(str(weight_path))


def save_weights(state: dict, out_path: Path) -> None:
    from safetensors.torch import save_file

    save_file(state, str(out_path), metadata={"format": "pt"})


def copy_assets(model_dir: Path, out_dir: Path) -> list[str]:
    copied: list[str] = []
    for path in sorted(model_dir.iterdir()):
        if path.is_dir() or path.name.startswith(".") or path.name == WEIGHT_FILE:
            continue
        if path.suffix in COPY_SUFFIXES:
            shutil.copy2(path, out_dir / path.name)
            copied.append(path.name)
    return copied


def to_fp16(state: dict, keep_fp32_hints: bool) -> tuple[dict, list[str]]:
    """转 fp16；keep_fp32_hints 为真时保留 norm/位置嵌入/soft prompt 之类张量的 fp32。"""
    converted: dict = {}
    kept: list[str] = []
    for key, tensor in state.items():
        if not tensor.is_floating_point():
            converted[key] = tensor
            continue
        if keep_fp32_hints and any(hint in key.lower() for hint in KEEP_FP32_HINTS):
            converted[key] = tensor
            kept.append(key)
            continue
        converted[key] = tensor.half()
    return converted, kept


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HuggingFace safetensors 权重转 fp16")
    parser.add_argument("--model", required=True, help="源模型目录（含 model.safetensors）")
    parser.add_argument("--out", required=True, help="输出目录")
    parser.add_argument("--dry-run", action="store_true", help="只读 header 打印计划")
    parser.add_argument("--keep-fp32-hints", action="store_true",
                        help="norm/layernorm/pos_emb/soft_prompt 类张量保持 fp32")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的输出")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_dir = Path(args.model)
    out_dir = Path(args.out)
    weight_path = model_dir / WEIGHT_FILE
    if not weight_path.exists():
        raise SystemExit(f"未找到权重文件: {weight_path}")

    source_mb = weight_path.stat().st_size / 1024**2
    shapes = read_shapes(weight_path)
    dtypes = read_dtypes(weight_path)
    float_keys = [key for key, dtype in dtypes.items() if dtype.startswith("F") or dtype == "BF16"]
    f32_keys = [key for key, dtype in dtypes.items() if dtype == "F32"]
    print(f"源权重:    {weight_path}  ({source_mb:.1f} MB)")
    print(f"张量:      {len(shapes)} 个（浮点 {len(float_keys)}，其中 fp32 {len(f32_keys)}）")

    if not f32_keys:
        print("注意: 源权重里没有 fp32 张量，可能已经是 fp16（无需转换）")
    preview = [key for key in float_keys if args.keep_fp32_hints
               and any(hint in key.lower() for hint in KEEP_FP32_HINTS)]
    if args.keep_fp32_hints:
        print(f"保留 fp32: {len(preview)} 个张量（norm / pos_emb / soft_prompt 类）")

    out_weight = out_dir / WEIGHT_FILE
    if args.dry_run:
        print(f"预计输出:  {out_weight}  约 {source_mb / 2:.1f} MB")
        print("dry-run：未写盘。")
        return 0

    if out_weight.exists() and not args.force:
        raise SystemExit(f"{out_weight} 已存在，加 --force 覆盖")

    out_dir.mkdir(parents=True, exist_ok=True)
    state = load_weights(weight_path)
    converted, kept = to_fp16(state, args.keep_fp32_hints)
    save_weights(converted, out_weight)
    copied = copy_assets(model_dir, out_dir)

    out_mb = out_weight.stat().st_size / 1024**2
    report = {
        "source": str(weight_path),
        "output": str(out_weight),
        "source_mb": round(source_mb, 1),
        "output_mb": round(out_mb, 1),
        "tensors": len(converted),
        "kept_fp32": kept,
        "keep_fp32_hints": args.keep_fp32_hints,
        "assets_copied": copied,
    }
    (out_dir / "to_fp16_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    out_dtypes = read_dtypes(out_weight)
    half = sum(1 for dtype in out_dtypes.values() if dtype == "F16")
    print(f"已写出:    {out_weight}  ({out_mb:.1f} MB)")
    print(f"fp16 张量: {half} / {len(out_dtypes)}，保留 fp32 {len(kept)} 个")
    print(f"复制文件:  {', '.join(copied)}")
    print("下一步: 导出 fp16 ONNX（scripts/export_onnx_fp16.py）后用 HMQuantool 量化")
    return 0


if __name__ == "__main__":
    sys.exit(main())
