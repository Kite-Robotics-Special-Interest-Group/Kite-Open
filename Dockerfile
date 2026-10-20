# Kite 开发环境镜像：把所有主机侧依赖与路径固定下来，避免"不同设备上出现不同的问题"
#
# 用途：
#   1) 跑单测 / 静态检查（CI 也用它）
#   2) 主机侧全链路：融合权重 → fp16 → 导出 fp16 ONNX（scripts/export_onnx_fp16.py）
#
# 构建： docker build -t kite-dev:latest .
# 运行： docker run --rm -v "$PWD:/kite" kite-dev:latest python -m pytest -q
#
# 注意：目标板（D3000M）内核缺 overlay/mqueue，容器在板上跑不起来 ——

# 基础镜像与包源都可以用 build-arg 替换（国内网络示例见 docs/container.md「国内网络」一节）：
#   docker build -t kite-dev:latest \
#     --build-arg BASE_IMAGE=docker.m.daocloud.io/library/python:3.10-slim \
#     --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple .
ARG BASE_IMAGE=python:3.10-slim
FROM ${BASE_IMAGE}

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG APT_MIRROR=

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/kite

# 模型侧依赖（opencv 头等）与 git（导出/脚本需要）；APT_MIRROR 非空时替换 Debian 源（国内网络用）
RUN if [ -n "${APT_MIRROR}" ]; then \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null \
      || sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends git libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 先装 CPU 版 torch：体积可控，且 amd64 / arm64 行为一致（GPU 训练另建镜像）
# 注意：pytorch 索引里没有 typing_extensions 等依赖，需把 PyPI 作为 extra index
RUN pip install --index-url ${TORCH_INDEX_URL} --extra-index-url ${PIP_INDEX_URL} torch torchvision

WORKDIR /kite
COPY requirements.txt ./
RUN pip install -i ${PIP_INDEX_URL} -r requirements.txt

COPY . .

# 默认动作：跑测试（CI 与本地验证一致）
CMD ["python", "-m", "pytest", "-q"]
