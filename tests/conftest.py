"""Shared fixtures for eval-lab tests: synthetic checkpoint construction."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest


def _write_safetensors(path: Path, tensors: dict[str, tuple[str, list[int], int]]) -> None:
    """Write a minimal valid .safetensors file (headers only, zero payload).

    ``tensors`` maps name -> (dtype, shape, byte_len).
    """
    header: dict[str, object] = {"__metadata__": {}}
    offset = 0
    per_tensor: dict[str, tuple[str, list[int], int, int]] = {}
    for name, (dtype, shape, byte_len) in tensors.items():
        per_tensor[name] = (dtype, shape, offset, offset + byte_len)
        offset += byte_len
    for name, (dtype, shape, start, end) in per_tensor.items():
        header[name] = {"dtype": dtype, "shape": shape, "data_offsets": [start, end]}
    raw = json.dumps(header).encode()
    with path.open("wb") as fh:
        fh.write(struct.pack("<Q", len(raw)))
        fh.write(raw)
        fh.write(b"\x00" * offset)
        # trailing 8-byte alignment
        while fh.tell() % 8 != 0:
            fh.write(b"\x00")


@pytest.fixture
def mini_checkpoint(tmp_path: Path) -> Path:
    """A tiny real sparse checkpoint dir: config + 2 safetensors shards."""
    ck = tmp_path / "ckpt"
    ck.mkdir(exist_ok=True)
    (ck / "config.json").write_text(
        json.dumps(
            {
                "model_type": "kimi_k3",
                "architectures": ["KimiK3ForCausalLM"],
                "num_hidden_layers": 93,
                "num_local_experts": 896,
                "num_experts_per_tok": 16,
                "quantization_config": {"quant_method": "mxfp4"},
            }
        ),
        encoding="utf-8",
    )
    _write_safetensors(
        ck / "model-00001-of-00002.safetensors",
        {
            "model.embed_tokens.weight": ("F16", [896, 4096], 896 * 4096 * 2),
            "model.layers.0.experts.0.w1.weight": ("F16", [1024, 4096], 1024 * 4096 * 2),
        },
    )
    _write_safetensors(
        ck / "model-00002-of-00002.safetensors",
        {"model.layers.0.experts.1.w1.weight": ("BF16", [1024, 4096], 1024 * 4096 * 2)},
    )
    return ck
