"""环境自检脚本：python scripts/check_env.py"""

import importlib
import importlib.util
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure") and not sys.stdout.isatty():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MIN_PYTHON = (3, 10)
REQUIRED = ["numpy", "yaml", "tqdm", "torch"]
OPTIONAL = ["onnxruntime", "openvino"]

REQUIRED_HINT = "pip install -r requirements.txt"


def check_python() -> bool:
    ok = sys.version_info >= MIN_PYTHON
    print(f"[{'OK' if ok else 'FAIL'}] Python {sys.version.split()[0]}")
    if not ok:
        print(f"       需要 Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 及以上")
    return ok


def check_module(name: str, required: bool = True) -> bool:
    if importlib.util.find_spec(name) is None:
        tag = "FAIL" if required else "SKIP"
        print(f"[{tag}] {name} 未安装")
        if required:
            print(f"       安装：{REQUIRED_HINT}")
        return not required
    mod = importlib.import_module(name)
    version = getattr(mod, "__version__", "unknown")
    print(f"[OK] {name} {version}")
    return True


def check_torch() -> bool:
    if not check_module("torch"):
        return False
    import torch

    if torch.cuda.is_available():
        print(f"       CUDA 可用: {torch.cuda.get_device_name(0)}")
    else:
        print("       CUDA 不可用（CPU 模式运行，端侧开发可接受）")
    return True


def check_project_layout() -> bool:
    root = Path(__file__).resolve().parent.parent
    ok = (root / "kite" / "__init__.py").exists()
    print(f"[{'OK' if ok else 'FAIL'}] 项目结构 kite/ （根目录: {root}）")
    return ok


def main() -> int:
    print("=" * 50)
    print("Kite 环境自检")
    print("=" * 50)

    results = [check_python(), check_project_layout()]
    for name in REQUIRED:
        if name == "torch":
            results.append(check_torch())
        else:
            results.append(check_module(name))
    for name in OPTIONAL:
        check_module(name, required=False)

    print("-" * 50)
    if all(results):
        print("环境检查通过，可以开始开发。")
        return 0
    print("存在失败项，请按提示修复后重试。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
