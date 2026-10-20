"""运行时后端注册表的轻量测试（公开镜像：仅 llamacpp / onnx）。"""

import pytest

from kite.runtime import BACKENDS, available_backends, get_backend, runtime_report


def test_registry_covers_public_backends():
    assert set(BACKENDS) == {"llamacpp", "onnx"}


def test_get_backend_rejects_unknown_name():
    with pytest.raises(KeyError):
        get_backend("cuda")


def test_backend_availability_is_boolean():
    for name, available in available_backends().items():
        assert isinstance(name, str)
        assert isinstance(available, bool)


def test_runtime_report_lists_backends():
    report = runtime_report()
    for name in BACKENDS:
        assert name in report
