"""把 X-VLA 权重固化为单本体：融合 soft prompt 与 domain 相关层。

用法：
  python scripts/fuse_softprompt.py --model weights/X-VLA-WidowX --domain 0 --out weights/X-VLA-WidowX-fused --dry-run
  python scripts/fuse_softprompt.py --model weights/X-VLA-WidowX --domain 0 --out weights/X-VLA-WidowX-fused

需 safetensors；读写整个 3.36 GB 权重，建议在内存 ≥16 GB 的机器上执行。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kite.models.softprompt import describe_shapes, fuse_state_dict, verify_fused  # noqa: E402

WEIGHT_FILE = "model.safetensors"
COPY_SUFFIXES: tuple[str, ...] = (".py", ".json", ".txt", ".model", ".md")


def read_weight_shapes(weight_path: Path) -> dict[str, tuple[int, ...]]:
    """只读 safetensors header 拿到键与形状，不加载张量数据（供 --dry-run 用）。"""
    try:
        from safetensors import safe_open
    except ImportError as exc:
        raise SystemExit("需要 safetensors：pip install safetensors") from exc
    with safe_open(str(weight_path), framework="pt") as handle:
        return {key: tuple(handle.get_slice(key).get_shape()) for key in handle.keys()}


def load_weights(model_dir: Path) -> dict:
    """读取 safetensors 权重。"""
    try:
        from safetensors.torch import load_file
    except ImportError as exc:
        raise SystemExit("需要 safetensors：pip install safetensors") from exc
    weight_path = model_dir / WEIGHT_FILE
    if not weight_path.exists():
        raise SystemExit(f"未找到权重文件: {weight_path}")
    return load_file(str(weight_path))


def save_weights(state: dict, out_dir: Path) -> Path:
    """写出融合后的 safetensors 权重。"""
    from safetensors.torch import save_file

    out_path = out_dir / WEIGHT_FILE
    save_file(state, str(out_path), metadata={"format": "pt"})
    return out_path


def read_model_config(model_dir: Path) -> dict:
    """读取 config.json。"""
    config_path = model_dir / "config.json"
    if not config_path.exists():
        raise SystemExit(f"未找到 {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def copy_assets(model_dir: Path, out_dir: Path) -> list[str]:
    """复制代码、分词器与配置等非权重文件。"""
    copied: list[str] = []
    for path in sorted(model_dir.iterdir()):
        if path.is_dir() or path.name.startswith(".") or path.name == WEIGHT_FILE:
            continue
        if path.suffix in COPY_SUFFIXES:
            shutil.copy2(path, out_dir / path.name)
            copied.append(path.name)
    return copied


def patch_config(out_dir: Path, domain_id: int) -> dict:
    """标记 config.json 为已融合。"""
    config_path = out_dir / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["fuse_soft_prompt"] = True
    config["fused_domain_id"] = domain_id
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="融合 X-VLA soft prompt / domain 参数为单本体权重")
    parser.add_argument("--model", required=True, help="原始 HuggingFace 快照目录")
    parser.add_argument("--out", required=True, help="融合权重输出目录")
    parser.add_argument("--domain", type=int, default=0, help="要固化的 domain_id")
    parser.add_argument("--len-soft-prompts", type=int, default=None, help="覆盖 config.json 的 len_soft_prompts")
    parser.add_argument("--hidden-size", type=int, default=None, help="覆盖 config.json 的 hidden_size")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不写盘")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_dir = Path(args.model)
    out_dir = Path(args.out)
    config = read_model_config(model_dir)
    len_soft_prompts = args.len_soft_prompts or int(config.get("len_soft_prompts", 0))
    hidden_size = args.hidden_size or int(config.get("hidden_size", 0))
    if len_soft_prompts <= 0 or hidden_size <= 0:
        raise SystemExit("需要 len_soft_prompts 与 hidden_size：检查 config.json 或用命令行覆盖")

    weight_path = model_dir / WEIGHT_FILE
    if not weight_path.exists():
        raise SystemExit(f"未找到权重文件: {weight_path}")

    shapes = read_weight_shapes(weight_path)
    info = describe_shapes(shapes)
    print(f"权重张量:     {len(shapes)} 个")
    print(f"num_domains: {info['num_domains']}")
    print(f"可融合层:     {', '.join(info['domain_linears']) or '无'}")
    print(f"固化 domain: {args.domain}  (len_soft_prompts={len_soft_prompts}, hidden_size={hidden_size})")
    if info["already_fused"]:
        raise SystemExit("该权重已融合过，无需重复处理")
    if not 0 <= args.domain < info["num_domains"]:
        raise SystemExit(f"domain 必须在 [0, {info['num_domains']}) 内")

    if args.dry_run:
        print("dry-run：未写盘。去掉 --dry-run 即可输出融合权重。")
        return 0

    state = load_weights(model_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    copied = copy_assets(model_dir, out_dir)
    fused = fuse_state_dict(state, args.domain, len_soft_prompts, hidden_size)
    report = verify_fused(fused, info["num_domains"], len_soft_prompts, hidden_size)
    if not report["ok"]:
        raise SystemExit(f"融合校验失败: {report['problems']}")

    weight_path = save_weights(fused, out_dir)
    patch_config(out_dir, args.domain)
    size_gb = weight_path.stat().st_size / 1024**3
    print(f"已写出:       {weight_path}  ({size_gb:.2f} GB)")
    print(f"复制文件:     {', '.join(copied)}")
    print(f"config.json:  fuse_soft_prompt=true, fused_domain_id={args.domain}")
    print("下一步: 导出 ONNX/GGUF 或上传网盘分发（见 weights/README.md）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
