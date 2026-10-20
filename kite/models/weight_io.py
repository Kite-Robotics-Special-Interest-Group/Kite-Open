"""safetensors 权重的通用读写与模型资产复制（融合 / 转 fp16 等脚本共用）。

读 header 只用到 ``safe_open``（不加载张量）；加载/保存张量需要 ``safetensors.torch``。
"""

from __future__ import annotations

import shutil
from pathlib import Path

WEIGHT_FILE = "model.safetensors"
COPY_SUFFIXES: tuple[str, ...] = (".py", ".json", ".txt", ".model", ".md")
MISSING_HINT = "需要 safetensors：pip install safetensors"


def _safe_open(weight_path: Path):
    try:
        from safetensors import safe_open  # noqa: PLC0415
    except ImportError as exc:
        raise SystemExit(MISSING_HINT) from exc
    return safe_open(str(weight_path), framework="pt")


def read_shapes(weight_path: Path) -> dict[str, tuple[int, ...]]:
    """只读 header 获取键与形状（供 --dry-run 用，不加载张量）。"""
    with _safe_open(weight_path) as handle:
        return {key: tuple(handle.get_slice(key).get_shape()) for key in handle.keys()}


def read_dtypes(weight_path: Path) -> dict[str, str]:
    """只读 header 获取每个张量的 dtype 字符串。"""
    with _safe_open(weight_path) as handle:
        return {key: str(handle.get_slice(key).get_dtype()) for key in handle.keys()}


def load_weights(weight_path: Path) -> dict:
    """加载 safetensors 权重。"""
    try:
        from safetensors.torch import load_file  # noqa: PLC0415
    except ImportError as exc:
        raise SystemExit(MISSING_HINT) from exc
    weight_path = Path(weight_path)
    if not weight_path.exists():
        raise SystemExit(f"未找到权重文件: {weight_path}")
    return load_file(str(weight_path))


def save_weights(state: dict, out_path: Path) -> Path:
    """写出 safetensors 权重，返回实际路径（自动创建父目录）。"""
    try:
        from safetensors.torch import save_file  # noqa: PLC0415
    except ImportError as exc:
        raise SystemExit(MISSING_HINT) from exc
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_file(state, str(out_path), metadata={"format": "pt"})
    return out_path


def copy_assets(model_dir: Path, out_dir: Path) -> list[str]:
    """复制代码、分词器与配置等非权重文件，返回已复制的文件名。"""
    copied: list[str] = []
    out_dir = Path(out_dir)
    for path in sorted(Path(model_dir).iterdir()):
        if path.is_dir() or path.name.startswith(".") or path.name == WEIGHT_FILE:
            continue
        if path.suffix in COPY_SUFFIXES:
            shutil.copy2(path, out_dir / path.name)
            copied.append(path.name)
    return copied
