# 容器化开发环境

把依赖与路径固定在镜像里，任何设备上跑同一组命令。

## 构建与运行

```bash
docker build -t kite-open:latest .
docker run --rm -v "$PWD:/kite" kite-open:latest python -m pytest -q
docker run --rm -v "$PWD:/kite" kite-open:latest python scripts/check_env.py
```

国内网络：基础镜像与包源可用 build-arg 替换（Docker Hub 不通时用镜像加速）：

```bash
docker build -t kite-open:latest \
  --build-arg BASE_IMAGE=docker.m.daocloud.io/library/python:3.10-slim \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple .
```

## 约定

- **权重不进镜像**：`.dockerignore` 已排除 `weights/`、`*.safetensors` 等；用 `-v` 挂载
- **路径以仓库根为基准**：脚本用 `Path(__file__)` 上溯定位，不假设当前目录
- **加载模型走 HF**：`AutoModel/AutoProcessor.from_pretrained(dir, trust_remote_code=True)`，
  不要直接 `import` 快照里的模块
