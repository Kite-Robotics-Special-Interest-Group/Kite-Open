# 环境搭建教程

面向零基础成员，覆盖从零到跑通 `pytest` 的完整流程。操作系统以 **Windows** 为主，macOS / Linux 差异会单独标注。

## 0. 需要准备的东西

| 工具 | 用途 | 下载 |
| --- | --- | --- |
| Python 3.10+ | 运行项目代码 | https://www.python.org/downloads/ |
| Git | 版本管理 | https://git-scm.com/downloads |
| Git LFS | 小体积二进制入库（备用，权重不走它） | https://git-lfs.com |
| （可选）显卡驱动 CUDA | GPU 加速训练 | NVIDIA 官网驱动 |

> 安装 Python 时勾选 **"Add python.exe to PATH"**；安装 Git 一路默认即可（会自动装 Git Bash 和凭据管理器）。

验证安装：

```bash
python --version   # 3.10 及以上
git --version
git lfs version    # 3.x，模型权重靠它管理
```

## 1. 获取代码

> **本仓库是私有仓库**：必须先让管理员 muzirin 邀请你加入（见 `docs/git-guide.md` 第 1.2 节），
> 在 GitHub 上打开仓库页面能看到内容后再进行下面的步骤。未受邀时 clone 会报
> `repository not found` 或 `Authentication failed`，这不是环境问题。

```bash
git lfs install    # 每台电脑只需执行一次，启用 LFS
git clone https://github.com/Kite-Robotics-Special-Interest-Group/Kite-Open.git
cd Kite
```

> 首次 clone 私有仓库会弹出浏览器登录（Git Credential Manager）；
> 若用 token 方式，用户名填 GitHub 用户名，密码位置粘贴 Personal Access Token。详见 `docs/git-guide.md` 第 1.3 节。
> `git lfs install` 仍要执行：仓库里若有走 LFS 的小文件，没装会拿到指针文本。

**权重不随 Git 下载**：`model.safetensors`（3.36 GB）通过网盘获取，
按 `weights/README.md` 放到 `weights/X-VLA-WidowX/` 并用 `SHA256SUMS.txt` 校验。

## 2. 创建虚拟环境（必做）

虚拟环境把本项目的依赖和系统里的其他 Python 隔离，避免版本互相污染。

**方式 A：venv（无需额外安装，推荐新手）**

```powershell
python -m venv .venv
.venv\Scripts\activate        # Windows PowerShell
# source .venv/bin/activate   # macOS / Linux / Git Bash
```

激活成功的标志是命令行开头出现 `(.venv)`。之后所有 `pip` 命令都装进这个环境。

**方式 B：conda**

```bash
conda create -n kite python=3.11 -y
conda activate kite
```

> `.venv/` 已在 `.gitignore` 中被忽略，不会被提交。

## 3. 安装依赖

### 3.1 国内镜像（国内网络强烈建议）

```bash
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3.2 安装 PyTorch（CPU 版，先跑通用）

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

**GPU 版（有 NVIDIA 显卡时）**：先确认驱动支持的 CUDA 版本，再装对应版本，例如 CUDA 12.1：

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

装完用下面命令验证，`True` 表示 GPU 可用：

```powershell
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

### 3.3 安装其余依赖

```bash
pip install -r requirements.txt
```

> `onnxruntime` / `openvino` 是端侧推理引擎，按需在 `requirements.txt` 中取消注释再安装，装一个即可。

### 3.4 连 GitHub / 下载慢的代理

若 `git clone`、`pip` 访问 GitHub 超时，且本机有代理（如 Clash，默认端口 7897）：

```bash
# 只对 github.com 走代理，不影响其他网站
git config --global http.https://github.com.proxy http://127.0.0.1:7897
```

> 反向情况：配了代理后若报 `schannel: failed to receive handshake, SSL/TLS connection failed`，
> 说明代理没有正常转发（代理软件未启动或规则不通），先去掉代理直连重试：
> `git config --global --unset http.https://github.com.proxy`

## 4. 验证环境

```bash
python scripts/check_env.py   # 检查 Python 版本、依赖、推理引擎
pytest -v                     # 跑通单元测试
```

两个命令都通过，环境即搭建完成。


## 5. 常见问题

| 现象 | 原因 / 解决 |
| --- | --- |
| `'python' 不是内部或外部命令` | 安装时没勾选 Add to PATH，重装或手动加 PATH |
| `pip` 下载超时 | 配置 3.1 国内镜像；GitHub 相关用 3.4 代理 |
| `torch.cuda.is_available()` 为 `False` | 驱动 / CUDA 版本不匹配，重装对应 `cu1xx` 版本 |
| 换了分支后 import 报错 | 依赖变了，重新 `pip install -r requirements.txt` |
| PowerShell 执行策略禁止激活脚本 | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| 权重文件太大 push 失败 | 权重本来就不该进 Git：`.gitignore` 已忽略 `*.safetensors` / `*.pt` 等，权重走网盘（见 `weights/README.md`、`docs/git-guide.md` 第 7 节） |
| clone 后 `weights/` 里没有 `model.safetensors` | 正常，权重不进 Git，按 `weights/README.md` 从网盘下载放入 |
| clone 下来的 `.pt` 是几行文本 | 该文件走了 LFS：安装 Git LFS 后 `git lfs pull` |

## 6. 环境规范（团队约定）

- 依赖只写进 `requirements.txt`，不要只装在自己电脑上不记录
- 新增第三方库：改 `requirements.txt` → 在自己的分支提交 → PR 时说明用途
- 模型权重放 `weights/`，**不进 Git**（网盘分发，见 `weights/README.md` 与 `docs/git-guide.md` 第 7 节）；实验大 checkpoint 同样不进仓库
- 数据集一律不进 Git（见 `.gitignore`）
- Python 统一 3.10 及以上
