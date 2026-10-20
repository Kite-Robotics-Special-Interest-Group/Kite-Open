"""Soft prompt 融合工具：把 X-VLA 的 domain 相关参数固化为单本体常量。

不依赖 torch：入参是 ``{键: 张量}`` 的字典（``torch.Tensor`` / ``numpy.ndarray`` 均可），
只做 ``reshape`` 与按 domain 切片，返回新字典，不修改入参。

对应关系（见 ``weights/X-VLA-WidowX/transformer.py``）：

- ``transformer.soft_prompt_hub.weight`` ``[num_domains, L*H]`` → ``transformer.soft_prompt.weight`` ``[L, H]``
- ``<prefix>.fc.weight`` / ``<prefix>.bias.weight`` ``[num_domains, ...]`` → ``[...]``（键名不变）
"""

from __future__ import annotations

from typing import Any, Mapping

PROMPT_HUB_KEY = "transformer.soft_prompt_hub.weight"
PROMPT_FUSED_KEY = "transformer.soft_prompt.weight"
DOMAIN_LINEAR_PREFIXES: tuple[str, ...] = (
    "transformer.action_encoder",
    "transformer.action_decoder",
    "transformer.vlm_proj",
    "transformer.aux_visual_proj",
)
WEIGHT_SUFFIX = "fc.weight"
BIAS_SUFFIX = "bias.weight"


def _shape(value: Any) -> tuple[int, ...]:
    """读取张量形状。"""
    shape = getattr(value, "shape", None)
    if shape is None:
        raise TypeError(f"张量缺少 shape 属性: {type(value)!r}")
    return tuple(int(dim) for dim in shape)


def _check_domain(domain_id: int, num_domains: int, key: str) -> None:
    if not 0 <= domain_id < num_domains:
        raise IndexError(f"domain_id={domain_id} 超出 {key} 的范围 [0, {num_domains})")


def describe_shapes(shapes: Mapping[str, tuple[int, ...]]) -> dict[str, Any]:
    """按 ``{键: 形状}`` 报告可融合的键、domain 数量与融合状态。"""
    prompt_shape = tuple(shapes[PROMPT_HUB_KEY]) if PROMPT_HUB_KEY in shapes else None
    prefixes = [prefix for prefix in DOMAIN_LINEAR_PREFIXES if f"{prefix}.{WEIGHT_SUFFIX}" in shapes]
    num_domains = prompt_shape[0] if prompt_shape else next(
        (tuple(shapes[f"{prefix}.{WEIGHT_SUFFIX}"])[0] for prefix in prefixes), 0
    )
    return {
        "num_domains": num_domains,
        "prompt_hub_key": PROMPT_HUB_KEY if prompt_shape else None,
        "prompt_flat_size": prompt_shape[1] if prompt_shape else None,
        "domain_linears": prefixes,
        "already_fused": PROMPT_FUSED_KEY in shapes and PROMPT_HUB_KEY not in shapes,
    }


def describe(state: Mapping[str, Any]) -> dict[str, Any]:
    """报告权重字典里可融合的键、domain 数量与融合状态。"""
    return describe_shapes({key: _shape(value) for key, value in state.items()})


def fuse_soft_prompt(
    state: Mapping[str, Any],
    domain_id: int,
    len_soft_prompts: int,
    hidden_size: int,
) -> dict[str, Any]:
    """把 ``soft_prompt_hub`` 指定 domain 的提示取出为 ``[L, H]`` 常量参数。"""
    if PROMPT_HUB_KEY not in state:
        raise KeyError(f"权重中不存在 {PROMPT_HUB_KEY}，可能已经融合过")
    hub = state[PROMPT_HUB_KEY]
    num_domains, flat_size = _shape(hub)
    _check_domain(domain_id, num_domains, PROMPT_HUB_KEY)
    if len_soft_prompts * hidden_size != flat_size:
        raise ValueError(
            f"len_soft_prompts({len_soft_prompts}) × hidden_size({hidden_size}) != {flat_size}"
        )
    fused = dict(state)
    fused[PROMPT_FUSED_KEY] = hub.reshape(num_domains, len_soft_prompts, hidden_size)[domain_id]
    del fused[PROMPT_HUB_KEY]
    return fused


def fuse_domain_linear(state: Mapping[str, Any], domain_id: int, prefix: str) -> dict[str, Any]:
    """把 ``DomainAwareLinear`` 的 domain 权重表切片成普通权重（键名保持）。"""
    fused = dict(state)
    touched = False
    for suffix in (WEIGHT_SUFFIX, BIAS_SUFFIX):
        key = f"{prefix}.{suffix}"
        if key not in fused:
            continue
        _check_domain(domain_id, _shape(fused[key])[0], key)
        fused[key] = fused[key][domain_id]
        touched = True
    if not touched:
        raise KeyError(f"{prefix} 不是 domain 相关层（缺少 {WEIGHT_SUFFIX}）")
    return fused


def fuse_state_dict(
    state: Mapping[str, Any],
    domain_id: int,
    len_soft_prompts: int,
    hidden_size: int,
    prefixes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """一次性融合 soft prompt 与全部 domain 相关层。"""
    fused = fuse_soft_prompt(state, domain_id, len_soft_prompts, hidden_size)
    for prefix in prefixes or DOMAIN_LINEAR_PREFIXES:
        if f"{prefix}.{WEIGHT_SUFFIX}" in fused:
            fused = fuse_domain_linear(fused, domain_id, prefix)
    return fused


def verify_fused(
    state: Mapping[str, Any],
    num_domains: int,
    len_soft_prompts: int,
    hidden_size: int,
) -> dict[str, Any]:
    """校验融合结果；``fc.weight`` 首维仍等于 num_domains 视为未融合（启发式）。"""
    problems: list[str] = []
    if PROMPT_HUB_KEY in state:
        problems.append(f"仍存在 {PROMPT_HUB_KEY}")
    if PROMPT_FUSED_KEY not in state:
        problems.append(f"缺少 {PROMPT_FUSED_KEY}")
    elif _shape(state[PROMPT_FUSED_KEY]) != (len_soft_prompts, hidden_size):
        problems.append(
            f"{PROMPT_FUSED_KEY} 形状为 {_shape(state[PROMPT_FUSED_KEY])}，期望 {(len_soft_prompts, hidden_size)}"
        )
    for prefix in DOMAIN_LINEAR_PREFIXES:
        key = f"{prefix}.{WEIGHT_SUFFIX}"
        if key in state and _shape(state[key])[0] == num_domains:
            problems.append(f"{key} 首维仍为 num_domains={num_domains}，疑似未融合")
    return {"ok": not problems, "problems": problems}
