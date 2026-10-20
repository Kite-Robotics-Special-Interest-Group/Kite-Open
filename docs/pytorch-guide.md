# PyTorch 速成（面向 Kite 项目）

面向零基础成员，30 分钟够用的 PyTorch 最小知识集，全部例子都贴近本仓库要做的事
（读 X-VLA 代码、改模型、跑推理、处理权重）。环境安装见 [setup.md](setup.md)。

> 一句话心智模型：**张量（数据）+ autograd（求导）+ `nn.Module`（层/模型）+ 训练/推理循环**。
> 本项目的端侧推理不训练，重点在「读懂 forward 的输入输出形状」和「正确处理 state_dict」。

## 1. 张量基础

```python
import torch

x = torch.tensor([[1.0, 2.0], [3.0, 4.0]])      # 从 Python 列表创建
z = torch.zeros(2, 3)                            # 全 0，[2, 3]
r = torch.randn(1, 30, 7)                        # 标准正态随机，[1, 30, 7]
a = torch.arange(10)                             # [10]

print(x.shape, x.dtype, x.device)                # torch.Size([2, 2]) torch.float32 cpu

# 形状操作（不会自动变形，必须显式）
x.reshape(4)                 # [4]     展平
x.unsqueeze(0)               # [1,2,2] 加一维（batch 维常用）
x.permute(1, 0)              # 转置
torch.cat([x, x], dim=0)     # 沿 dim 拼接 → [4, 2]
x[:, 0]                      # 索引/切片，和 numpy 一致

# 常用数学
x * 2 + 1
x @ x.T                      # 矩阵乘（本项目里 Linear 内部就是它）
x.mean(), x.sum(dim=-1)      # 归约
x.softmax(dim=-1)
```

`dtype` 很关键：本项目权重是 **fp32**，端侧会转 **fp16**；不同 dtype 相加会直接报错。

## 2. 自动求导（autograd）

```python
w = torch.randn(3, requires_grad=True)
loss = (w ** 2).sum()
loss.backward()              # 反向：把梯度写到 w.grad
print(w.grad)

# 推理时必须关掉求导：更快、更省内存
with torch.no_grad():        # 或 torch.inference_mode()
    y = w * 2
print(y.requires_grad)       # False

loss.detach()                # 从计算图里摘出来（记指标/存盘时用）
```

> 见 `weights/X-VLA-WidowX/modeling_xvla.py:174` 的 `@torch.no_grad()`：`generate_actions` 就是推理路径。

## 3. 模型：`nn.Module`

```python
import torch.nn as nn

class Head(nn.Module):
    def __init__(self, hidden: int, out: int):
        super().__init__()
        self.norm = nn.LayerNorm(hidden)
        self.fc = nn.Linear(hidden, out)

    def forward(self, x):            # x: [B, H] → [B, out]
        return self.fc(self.norm(x))

head = Head(8, 3)
print(sum(p.numel() for p in head.parameters()))   # 参数量

# 调用模型 = 调 forward（不要直接写 model.forward(x)）
y = head(torch.randn(4, 8))
```

本项目里你会遇到的三类层：

| 层 | 用途 | 例子 |
| --- | --- | --- |
| `nn.Linear` | 全连接（本项目 90% 参数） | `transformer.py:69` 的 `fc1/fc2` |
| `nn.Embedding` | 查表（本项目存 soft prompt 与 domain 权重） | `transformer.py:336` `soft_prompt_hub` |
| `nn.LayerNorm` | 归一化 | `transformer.py:260` |

`nn.Embedding` 的本质是"按 id 取行"，所以端侧要**固化**成常量（见 [softprompt-plan.md](softprompt-plan.md)）。

## 4. 训练循环骨架（本项目基本用不到，但要看懂）

```python
from torch.utils.data import Dataset, DataLoader

class Toy(Dataset):
    def __init__(self, n=256):
        self.x = torch.randn(n, 8)
        self.y = torch.randn(n, 3)
    def __len__(self):  return len(self.x)
    def __getitem__(self, i):  return self.x[i], self.y[i]

model = Head(8, 3)
loader = DataLoader(Toy(), batch_size=32, shuffle=True, num_workers=0)  # Windows 上先设 0
opt = torch.optim.Adam(model.parameters(), lr=1e-3)
crit = nn.MSELoss()

model.train()
for epoch in range(2):
    for xb, yb in loader:
        opt.zero_grad()          # ① 清梯度（不清会累加）
        loss = crit(model(xb), yb)
        loss.backward()          # ② 反向求导
        opt.step()               # ③ 更新参数

model.eval()                     # 推理前切换：关闭 dropout 等
with torch.no_grad():
    print(crit(model(torch.randn(4, 8)), torch.randn(4, 3)).item())
```

固定顺序记法：**zero_grad → forward → loss → backward → step**。

## 5. 推理、保存与加载（本项目重点）

```python
# 保存/加载 state_dict（只存权重，不存代码）
torch.save(model.state_dict(), "head.pt")
state = torch.load("head.pt", map_location="cpu", weights_only=True)   # torch 2.6+ 默认 weights_only=True
model2 = Head(8, 3)
model2.load_state_dict(state)             # 键必须严格匹配

# 本项目：HF 快照是 safetensors，取权重更安全
from safetensors.torch import load_file, save_file
weights = load_file("weights/X-VLA-WidowX/model.safetensors")
print(len(weights), list(weights)[:3])       # 903 个张量
print(weights["transformer.soft_prompt_hub.weight"].shape)   # [30, 32768]

# 键名带前缀时用 strict=False 或手工裁剪
missing, unexpected = model2.load_state_dict(state, strict=False)
print(missing, unexpected)
```

> 直接改 `state_dict`（不实例化模型）是本节最实用的技巧：
> `scripts/fuse_softprompt.py` 就是这么处理 3.36 GB 权重的——省内存，也避开 remote code 依赖。

## 6. 设备与精度

```python
device = "cuda" if torch.cuda.is_available() else "cpu"
model = model.to(device)

x = torch.randn(4, 8, device=device)          # 数据和模型必须在同一 device
# 混合精度（GPU 训练常用；CPU 推理路径本项目用 fp32）
with torch.autocast("cuda", dtype=torch.float16):
    y = model(x)

# CPU 上没有 CUDA autocast（会打印 warning 并退化为 fp32）；
# CPU 想省内存时可用：with torch.autocast("cpu", dtype=torch.bfloat16):（依赖 CPU 是否支持 bf16）

# 权重整体转 fp16（端侧量化前的第一步，见 todo.md）
fp16_state = {k: (v.half() if v.is_floating_point() else v) for k, v in weights.items()}
```

`fp32 → fp16` 会让数值范围变小：LayerNorm、位置嵌入这类敏感参数是否保留 fp32 需要实验确认（`todo.md` 待确认第 4 条）。

## 7. 性能与调试小抄

```python
torch.set_num_threads(8)                 # CPU 推理线程数（D3000M 八核）
torch.backends.mkldnn.enabled = True     # x86 上走 MKL-DNN
with torch.profiler.profile() as prof:   # 找瓶颈
    model(x)
print(prof.key_averages().table(sort_by="cpu_time_total", row_limit=10))
```

| 报错 | 原因 / 解决 |
| --- | --- |
| `Expected all tensors to be on the same device` | 模型和数据 device 不一致：统一 `.to(device)` |
| `expected scalar type Float but found Half` | dtype 混用：`x.to(torch.float32)` 或统一 fp16 |
| `size mismatch for ...` | 结构或 config 与权重不匹配：检查 `num_domains`/`hidden_size` |
| 推理越来越慢/爆内存 | 忘了 `torch.no_grad()`，计算图在累积 |
| `CUDA out of memory` | 减小 batch / `steps`，或 `.cpu()` 跑小图 |
| `DataLoader` 在 Windows 卡死 | `num_workers=0`（默认就是 0） |

## 8. 与本仓库直接相关的三件事

1. **读形状**：`SoftPromptedTransformer.forward`（`transformer.py:341`）的输入是
   `domain_id [B]`、`vlm_features [B, T_vlm, D]`、`aux_visual_inputs [B, T_aux, D]`、
   `action_with_noise [B, T_action, dim_action]`、`proprio [B, dim_propio]`、`t [B]`，
   输出 `[B, T_action, dim_action]`。
2. **跑推理**：`XVLA.generate_actions(steps=10)`（`modeling_xvla.py:175`）是「迭代去噪」循环，
   每一步都在调 `transformer`；`t` 从 `i/steps` 递减到 `1/steps`。
3. **改权重**：用 `kite/models/softprompt.py` 的纯字典操作做融合/切片，跑
   `python scripts/fuse_softprompt.py --model weights/X-VLA-WidowX --domain 0 --out <out> --dry-run`。

## 9. 自查练习

- [ ] 打印 `weights["transformer.action_decoder.bias.weight"].shape`，解释为什么首维是 `num_domains`
- [ ] 用纯 `state_dict` 操作（不加载模型）取出 `domain_id=0` 的 soft prompt，形状应为 `[32, 1024]`
- [ ] 把 `Head(8, 3)` 转 fp16 跑一次前向，观察输出 dtype 与数值差异

## 10. API 速查

```python
torch.tensor / zeros / ones / randn / arange        # 创建
x.shape / dtype / device / reshape / view / unsqueeze / permute / cat / split
x.mean / sum / softmax / matmul(@) / clamp / no_grad
requires_grad / backward / detach / zero_grad
nn.Linear / nn.Embedding / nn.LayerNorm / nn.Dropout / nn.ModuleList
model.train() / model.eval() / model.parameters() / model.state_dict() / load_state_dict()
torch.save / torch.load / safetensors.torch.load_file / save_file
optim.Adam / lr_scheduler / loss.backward() / optimizer.step()
```

官方教程（先看 60 分钟入门）：<https://pytorch.org/tutorials/beginner/basics/intro.html>
