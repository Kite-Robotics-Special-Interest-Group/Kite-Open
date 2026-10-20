"""soft prompt 融合工具的单测（合成小张量，不需要真实权重）。"""

import numpy as np
import pytest

from kite.models.softprompt import (
    PROMPT_FUSED_KEY,
    PROMPT_HUB_KEY,
    describe,
    fuse_domain_linear,
    fuse_soft_prompt,
    fuse_state_dict,
    verify_fused,
)

NUM_DOMAINS = 3
LEN_SOFT_PROMPTS = 2
HIDDEN_SIZE = 4
IN_FEATURES = 5
OUT_FEATURES = 6
DOMAIN = 2


def make_state() -> dict[str, np.ndarray]:
    return {
        PROMPT_HUB_KEY: np.arange(
            NUM_DOMAINS * LEN_SOFT_PROMPTS * HIDDEN_SIZE, dtype=np.float32
        ).reshape(NUM_DOMAINS, LEN_SOFT_PROMPTS * HIDDEN_SIZE),
        "transformer.action_encoder.fc.weight": np.arange(
            NUM_DOMAINS * OUT_FEATURES * IN_FEATURES, dtype=np.float32
        ).reshape(NUM_DOMAINS, OUT_FEATURES * IN_FEATURES),
        "transformer.action_encoder.bias.weight": np.arange(
            NUM_DOMAINS * OUT_FEATURES, dtype=np.float32
        ).reshape(NUM_DOMAINS, OUT_FEATURES),
        "transformer.action_decoder.fc.weight": np.zeros((NUM_DOMAINS, OUT_FEATURES * IN_FEATURES), dtype=np.float32),
        "transformer.action_decoder.bias.weight": np.zeros((NUM_DOMAINS, OUT_FEATURES), dtype=np.float32),
        "vlm.language_model.shared.weight": np.zeros((2, 2), dtype=np.float32),
    }


def test_describe_reports_fusable_layers():
    info = describe(make_state())
    assert info["num_domains"] == NUM_DOMAINS
    assert info["domain_linears"] == ["transformer.action_encoder", "transformer.action_decoder"]
    assert info["already_fused"] is False


def test_fuse_soft_prompt_slices_domain_and_keeps_input():
    state = make_state()
    fused = fuse_soft_prompt(state, DOMAIN, LEN_SOFT_PROMPTS, HIDDEN_SIZE)
    assert PROMPT_HUB_KEY not in fused
    assert fused[PROMPT_FUSED_KEY].shape == (LEN_SOFT_PROMPTS, HIDDEN_SIZE)
    expected = state[PROMPT_HUB_KEY].reshape(NUM_DOMAINS, LEN_SOFT_PROMPTS, HIDDEN_SIZE)[DOMAIN]
    assert np.array_equal(fused[PROMPT_FUSED_KEY], expected)
    assert PROMPT_HUB_KEY in state


def test_fuse_soft_prompt_rejects_bad_domain_and_shape():
    state = make_state()
    with pytest.raises(IndexError):
        fuse_soft_prompt(state, NUM_DOMAINS, LEN_SOFT_PROMPTS, HIDDEN_SIZE)
    with pytest.raises(ValueError):
        fuse_soft_prompt(state, 0, LEN_SOFT_PROMPTS + 1, HIDDEN_SIZE)
    with pytest.raises(KeyError):
        fuse_soft_prompt(fuse_soft_prompt(state, 0, LEN_SOFT_PROMPTS, HIDDEN_SIZE), 0, LEN_SOFT_PROMPTS, HIDDEN_SIZE)


def test_fuse_domain_linear_flattens_tables():
    state = make_state()
    fused = fuse_domain_linear(state, DOMAIN, "transformer.action_encoder")
    assert fused["transformer.action_encoder.fc.weight"].shape == (OUT_FEATURES * IN_FEATURES,)
    assert fused["transformer.action_encoder.bias.weight"].shape == (OUT_FEATURES,)
    assert np.array_equal(
        fused["transformer.action_encoder.fc.weight"], state["transformer.action_encoder.fc.weight"][DOMAIN]
    )


def test_fuse_domain_linear_rejects_non_domain_layer():
    with pytest.raises(KeyError):
        fuse_domain_linear(make_state(), 0, "vlm.language_model")


def test_fuse_state_dict_and_verify():
    state = make_state()
    fused = fuse_state_dict(state, DOMAIN, LEN_SOFT_PROMPTS, HIDDEN_SIZE)
    assert describe(fused)["already_fused"] is True
    assert verify_fused(fused, NUM_DOMAINS, LEN_SOFT_PROMPTS, HIDDEN_SIZE)["ok"] is True


def test_verify_fused_flags_unfused_state():
    report = verify_fused(make_state(), NUM_DOMAINS, LEN_SOFT_PROMPTS, HIDDEN_SIZE)
    assert report["ok"] is False
    assert len(report["problems"]) >= 3
