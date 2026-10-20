"""llama.cpp 运行时后端：在飞腾 D3000M（aarch64）上跑 GGUF 模型。"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

BINARY_CANDIDATES: tuple[str, ...] = ("llama-cli", "llama-server", "main")
EXECUTABLE_SUFFIXES: tuple[str, ...] = ("", ".exe", ".bat", ".cmd", ".ps1", ".sh")
PYTHON_BINDING = "llama_cpp"


def _resolve_binary(name: str) -> str | None:
    """只在后缀合法时接受 shutil.which 的结果，避免误命中 main.CPL 之类的同名文件。"""
    found = shutil.which(name)
    if found and Path(found).suffix.lower() in EXECUTABLE_SUFFIXES:
        return found
    return None


@dataclass
class LlamaCppConfig:
    """llama.cpp 运行参数，字段与 CLI 选项一一对应。"""

    binary: str | None = None
    model_path: str | None = None
    n_gpu_layers: int = 0
    threads: int = 0
    ctx_size: int = 4096
    device: str | None = None
    backend_dir: str | None = None
    extra_args: list[str] = field(default_factory=list)


class LlamaCppRuntime:
    """包装 llama-cli / llama-server，并提供可用性与设备查询。"""

    def __init__(self, config: LlamaCppConfig | None = None) -> None:
        self.config = config or LlamaCppConfig()
        self._binary: str | None = None

    def binary(self) -> str | None:
        """解析 llama.cpp 可执行文件路径。"""
        if self._binary:
            return self._binary
        if self.config.binary:
            path = Path(self.config.binary)
            self._binary = str(path) if path.exists() else _resolve_binary(self.config.binary)
            return self._binary
        for name in BINARY_CANDIDATES:
            self._binary = _resolve_binary(name)
            if self._binary:
                return self._binary
        return None

    def python_binding_available(self) -> bool:
        """是否安装了 llama-cpp-python。"""
        return importlib.util.find_spec(PYTHON_BINDING) is not None

    def available(self) -> bool:
        """本机是否可用 llama.cpp 运行时。"""
        return self.binary() is not None or self.python_binding_available()

    def _run(self, args: list[str], timeout: int) -> tuple[int, str]:
        binary = self.binary()
        if binary is None:
            raise RuntimeError("未找到 llama.cpp 可执行文件，先在板端编译（见 docs/runtime-llamacpp.md）")
        result = subprocess.run(
            [binary, *args], capture_output=True, text=True, timeout=timeout, check=False
        )
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        return result.returncode, output

    def version(self, timeout: int = 30) -> str | None:
        """读取 llama.cpp 版本。"""
        try:
            _, output = self._run(["--version"], timeout)
        except (OSError, subprocess.SubprocessError, RuntimeError):
            return None
        return output.splitlines()[0].strip() if output else None

    def list_devices(self, timeout: int = 60) -> list[str]:
        """列出可用后端设备（含后摩等插件后端）。"""
        try:
            _, output = self._run(["--list-devices"], timeout)
        except (OSError, subprocess.SubprocessError, RuntimeError):
            return []
        return [line.strip() for line in output.splitlines() if line.strip()]

    def _common_args(self) -> list[str]:
        cfg = self.config
        if not cfg.model_path:
            raise ValueError("model_path 未配置")
        args = ["-m", cfg.model_path, "-c", str(cfg.ctx_size), "-ngl", str(cfg.n_gpu_layers)]
        if cfg.threads > 0:
            args += ["-t", str(cfg.threads)]
        if cfg.device:
            args += ["--device", cfg.device]
        args += cfg.extra_args
        return args

    def build_cli_command(self, prompt: str, n_predict: int = 128) -> list[str]:
        """构造单轮推理命令。"""
        binary = self.binary() or "llama-cli"
        return [
            binary,
            *self._common_args(),
            "-p",
            prompt,
            "-n",
            str(n_predict),
            "-no-cnv",
            "--no-display-prompt",
        ]

    def build_server_command(self, host: str = "127.0.0.1", port: int = 8080) -> list[str]:
        """构造 OpenAI 兼容服务命令。"""
        binary = self.binary() or "llama-server"
        return [binary, *self._common_args(), "--host", host, "--port", str(port)]

    def generate(self, prompt: str, n_predict: int = 128, timeout: int = 600) -> str:
        """执行一次 CLI 推理并返回文本输出。"""
        binary = self.binary()
        if binary is None:
            raise RuntimeError("未找到 llama.cpp 可执行文件")
        command = self.build_cli_command(prompt, n_predict)
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        if result.returncode != 0:
            raise RuntimeError(f"llama.cpp 推理失败（exit={result.returncode}）: {output[-1000:]}")
        return output

    def describe(self) -> dict:
        """汇总 llama.cpp 后端状态，供 check_runtime 输出。"""
        return {
            "available": self.available(),
            "binary": self.binary(),
            "python_binding": self.python_binding_available(),
            "version": self.version() if self.binary() else None,
            "devices": self.list_devices() if self.binary() else [],
            "model_path": self.config.model_path,
        }
