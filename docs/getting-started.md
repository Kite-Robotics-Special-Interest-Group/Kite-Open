# 快速上手（公开镜像）

本镜像聚焦**与硬件无关**的部分：把 X-VLA 的权重整理成单本体、转 fp16，并验证工具链。
端侧量化/编译/部署属于私有仓库范围，本文不涉及。

## 0. 准备

- Python ≥ 3.10，或 Docker（推荐）
- 权重：`weights/X-VLA-WidowX/model.safetensors`（3.36 GB，通过网盘获取，**不在仓库里**）

## 1. 容器里跑测试

```bash
docker build -t kite-open:latest .
docker run --rm -v "$PWD:/kite" kite-open:latest python -m pytest -q
# 期望全部通过
```

## 2. 融合 soft prompt（单本体）

X-VLA 用 30 组 soft prompt 编码本体先验。端侧只服务一个本体时，可以固化：

```bash
python scripts/fuse_softprompt.py \
    --model weights/X-VLA-WidowX --domain 0 \
    --out weights/X-VLA-WidowX-fused --dry-run   # 先看计划
python scripts/fuse_softprompt.py \
    --model weights/X-VLA-WidowX --domain 0 \
    --out weights/X-VLA-WidowX-fused             # 实际写盘（约 3.3 GB）
```

**预期**：输出目录的 `model.safetensors` 里
`transformer.soft_prompt.weight` 形状为 `[32, 1024]`，
`transformer.action_encoder.fc.weight` 从 `[30, 73728]` 变成 `[73728]`。

## 3. 转 fp16

```bash
python scripts/to_fp16.py \
    --model weights/X-VLA-WidowX-fused \
    --out weights/X-VLA-WidowX-fp16
```

**预期**：约 1.68 GB，903 个张量全部 fp16；报告写入 `to_fp16_report.json`。

## 4. 运行时抽象

```python
from kite.runtime import get_backend, available_backends

print(available_backends())          # {"llamacpp": bool, "onnx": bool}
print(get_backend("onnx").describe())  # onnxruntime 版本与可用的执行提供程序
```

## 5. 接着去哪

- 环境与依赖：[docs/setup.md](setup.md)
- 容器化：[docs/container.md](container.md)
- Git 协作：[docs/git-guide.md](git-guide.md)、[CONTRIBUTING.md](../CONTRIBUTING.md)
