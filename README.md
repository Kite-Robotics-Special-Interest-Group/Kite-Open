# Kite（公开镜像）

> 这是 **Kite 项目**的公开镜像：只包含通用的模型侧工具、端侧运行时抽象与文档。
> 完整的端侧部署链路（量化 / 编译 / 设备运行）与实测数据在私有主仓库中维护。

Kite 是面向端侧设备的轻量级 VLA（Vision-Language-Action）模型与运行时框架。

## 这里有什么

| 目录 / 文件 | 内容 |
| --- | --- |
| `kite/models/softprompt.py` | X-VLA soft prompt / domain 参数融合工具（单本体固化） |
| `kite/runtime/` | 运行时抽象：平台检测（llama.cpp）、ONNX Runtime 后端 |
| `scripts/fuse_softprompt.py` | 融合 soft prompt 的命令行工具 |
| `scripts/to_fp16.py` | safetensors 权重转 fp16 |
| `scripts/check_env.py` | 环境自检 |
| `tests/` | 单元测试（`python -m pytest -q`） |
| `docs/` | 环境搭建、容器、PyTorch 速成、Git 教程 |

## 快速开始

```bash
git clone https://github.com/Kite-Robotics-Special-Interest-Group/Kite-Open.git
cd Kite-Open

# 容器内跑测试（推荐）
docker build -t kite-open:latest .
docker run --rm -v "$PWD:/kite" kite-open:latest python -m pytest -q

# 或本机
pip install -r requirements.txt
python -m pytest -q
```

软件层面的完整流程（融合 → fp16 → 固定形状 ONNX → 端侧部署）见
[`docs/getting-started.md`](docs/getting-started.md)。

## 许可

代码采用 [MIT](LICENSE)。第三方项目与分发范围见 [NOTICE](NOTICE)。

## 组织

- 主页：[Kite Robotics Special Interest Group](https://github.com/Kite-Robotics-Special-Interest-Group)
- 贡献流程：[CONTRIBUTING.md](CONTRIBUTING.md)
