"""端侧推理运行时（公开镜像）。

本镜像只包含与硬件无关的后端：

- ``llamacpp``: GGUF 模型，llama.cpp（CPU 路径）
- ``onnx``: ONNX Runtime（CPU / 厂商执行提供程序）

完整的设备端部署（厂商工具链、设备二进制）在私有主仓库中维护。
"""

from __future__ import annotations

from typing import Any

from .llamacpp import LlamaCppConfig, LlamaCppRuntime
from .onnx_backend import OnnxBackend, OnnxConfig

BACKENDS: dict[str, type] = {
    "llamacpp": LlamaCppRuntime,
    "onnx": OnnxBackend,
}

CONFIG_TYPES: dict[str, type] = {
    "llamacpp": LlamaCppConfig,
    "onnx": OnnxConfig,
}


def get_backend(name: str, config: Any | None = None) -> Any:
    """按名称创建后端实例。"""
    if name not in BACKENDS:
        raise KeyError(f"未知后端 {name!r}，可选: {sorted(BACKENDS)}")
    return BACKENDS[name](config)


def available_backends() -> dict[str, bool]:
    """各后端在当前主机上的可用性。"""
    return {name: bool(get_backend(name).available()) for name in BACKENDS}


def runtime_report() -> str:
    """后端可用性报告。"""
    lines = ["=== 后端可用性 ==="]
    for name, ok in available_backends().items():
        lines.append(f"{name:<10} {'可用' if ok else '不可用'}")
    return "\n".join(lines)


__all__ = [
    "BACKENDS",
    "CONFIG_TYPES",
    "LlamaCppConfig",
    "LlamaCppRuntime",
    "OnnxBackend",
    "OnnxConfig",
    "available_backends",
    "get_backend",
    "runtime_report",
]
