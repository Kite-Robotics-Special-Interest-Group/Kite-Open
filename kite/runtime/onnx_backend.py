"""ONNX 运行时后端：主机 CPU 推理，并做面向 M50/TCIM 的编译前检查。"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

ONNX_RUNTIME_MODULE = "onnxruntime"
ONNX_MODULE = "onnx"
CPU_PROVIDER = "CPUExecutionProvider"
HOUMO_PROVIDER_NAMES: tuple[str, ...] = (
    "HoumoExecutionProvider",
    "HmExecutionProvider",
    "Xh2ExecutionProvider",
)
MIN_GLIBC_FOR_AARCH64_WHEEL = (2, 28)


@dataclass
class OnnxConfig:
    """ONNX 运行配置。providers 留空时自动挑选（优先后摩 EP）。"""

    model_path: str | None = None
    providers: list[str] = field(default_factory=list)
    provider_options: list[dict[str, Any]] | None = None
    intra_op_threads: int | None = None
    static_shapes: bool = True


class OnnxBackend:
    """ONNX Runtime 封装，附带后摩工具链要求的固定形状检查。"""

    name = "onnx"

    def __init__(self, config: OnnxConfig | None = None) -> None:
        self.config = config or OnnxConfig()
        self._session: Any = None

    def runtime(self) -> Any:
        """导入 onnxruntime（未安装时抛出带提示的错误）。"""
        if importlib.util.find_spec(ONNX_RUNTIME_MODULE) is None:
            raise RuntimeError(
                "未安装 onnxruntime：pip install onnxruntime（aarch64 用 manylinux_2_28 wheel）"
            )
        import onnxruntime  # noqa: PLC0415

        return onnxruntime

    def available(self) -> bool:
        """本机是否可用 ONNX Runtime。"""
        return importlib.util.find_spec(ONNX_RUNTIME_MODULE) is not None

    def version(self) -> str | None:
        """onnxruntime 版本号。"""
        if not self.available():
            return None
        return getattr(self.runtime(), "__version__", None)

    def available_providers(self) -> list[str]:
        """当前构建支持的执行提供程序。"""
        if not self.available():
            return []
        return list(self.runtime().get_available_providers())

    def registered_providers(self) -> list[str]:
        """当前已注册的执行提供程序。"""
        if not self.available():
            return []
        return list(self.runtime().get_all_providers())

    def houmo_provider(self) -> str | None:
        """返回后摩执行提供程序名称（如随 SDK 提供）。"""
        providers = set(self.available_providers())
        for name in HOUMO_PROVIDER_NAMES:
            if name in providers:
                return name
        return None

    def default_providers(self) -> list[str]:
        """默认执行提供程序：有后摩 EP 则优先，否则纯 CPU。"""
        houmo = self.houmo_provider()
        return [houmo, CPU_PROVIDER] if houmo else [CPU_PROVIDER]

    def create_session(self, model_path: str | None = None, providers: list[str] | None = None) -> Any:
        """创建推理会话。"""
        path = model_path or self.config.model_path
        if not path:
            raise ValueError("model_path 未配置")
        session_options = self.runtime().SessionOptions()
        if self.config.intra_op_threads:
            session_options.intra_op_num_threads = self.config.intra_op_threads
        chosen = providers or self.config.providers or self.default_providers()
        kwargs: dict[str, Any] = {"sess_options": session_options, "providers": chosen}
        if self.config.provider_options:
            kwargs["provider_options"] = self.config.provider_options
        self._session = self.runtime().InferenceSession(path, **kwargs)
        return self._session

    def describe_model(self, model_path: str | None = None) -> list[dict[str, Any]]:
        """列出模型输入输出名称、形状与类型（优先用 onnx 解析静态图）。"""
        path = model_path or self.config.model_path
        if not path:
            raise ValueError("model_path 未配置")
        if importlib.util.find_spec(ONNX_MODULE) is not None:
            return self._describe_with_onnx(path)
        session = self.create_session(path)
        return [
            {
                "name": value.name,
                "shape": list(value.shape),
                "dtype": str(value.type),
                "direction": direction,
            }
            for direction, values in (("input", session.get_inputs()), ("output", session.get_outputs()))
            for value in values
        ]

    def _describe_with_onnx(self, path: str) -> list[dict[str, Any]]:
        import onnx  # noqa: PLC0415

        graph = onnx.load(path).graph
        tensor_types = {value.name: value.type for value in (*graph.input, *graph.output)}
        result: list[dict[str, Any]] = []
        for direction, values in (("input", graph.input), ("output", graph.output)):
            for value in values:
                if value.name.endswith("_dtype") or value.name in {v.name for v in graph.initializer}:
                    continue
                dims: list[Any] = []
                tensor_type = tensor_types[value.name].tensor_type
                for dim in tensor_type.shape.dim:
                    dims.append(dim.dim_value if dim.HasField("dim_value") else dim.dim_param or None)
                result.append(
                    {
                        "name": value.name,
                        "shape": dims,
                        "dtype": tensor_type.elem_type,
                        "direction": direction,
                    }
                )
        return result

    def dynamic_inputs(self, model_path: str | None = None) -> list[str]:
        """返回含动态维度（符号或 -1）的输入名。"""
        dynamic: list[str] = []
        for item in self.describe_model(model_path):
            if item["direction"] != "input":
                continue
            if any(not isinstance(dim, int) or dim <= 0 for dim in item["shape"]):
                dynamic.append(item["name"])
        return dynamic

    def static_shape_report(self, model_path: str | None = None) -> dict[str, Any]:
        """面向后摩 TCIM 编译的形状检查：M50 只接受固定形状输入。"""
        path = model_path or self.config.model_path
        if not path or not Path(path).exists():
            return {"ok": False, "reason": f"模型文件不存在: {path}", "dynamic_inputs": []}
        dynamic = self.dynamic_inputs(path)
        report = {
            "model": path,
            "dynamic_inputs": dynamic,
            "ok": not dynamic,
        }
        if dynamic:
            report["reason"] = (
                "模型含动态维度，后摩 M50 编译要求固定形状；"
                "请导出时固定 batch/seq/图像尺寸（见 docs/runtime-onnx.md）"
            )
        return report

    def run(self, inputs: Mapping[str, Any], model_path: str | None = None) -> dict[str, Any]:
        """执行一次推理。"""
        session = self._session or self.create_session(model_path)
        names = {value.name for value in session.get_inputs()}
        feed = {key: value for key, value in inputs.items() if key in names}
        missing = names - set(feed)
        if missing:
            raise ValueError(f"缺少输入: {sorted(missing)}")
        outputs = session.run(None, feed)
        return {
            value.name: array
            for value, array in zip(session.get_outputs(), outputs, strict=False)
        }

    def describe(self) -> dict[str, Any]:
        """汇总 ONNX 后端状态，供 check_runtime 输出。"""
        return {
            "available": self.available(),
            "version": self.version(),
            "available_providers": self.available_providers(),
            "registered_providers": self.registered_providers(),
            "houmo_provider": self.houmo_provider(),
            "model_path": self.config.model_path,
        }
