"""Lightweight checkpoint inspection (spec 3.2, 3.3).

Reads only SafeTensors headers plus config/tokenizer metadata — never tensor
payloads — so oversized checkpoints can be classified without full loads.
"""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any

from eval_lab.schemas.model_asset import CheckpointInspection, InspectionIssue

# Approximate bytes per element by dtype name.
_DTYPE_BYTES: dict[str, float] = {
    "F64": 8.0,
    "I64": 8.0,
    "U64": 8.0,
    "F32": 4.0,
    "U32": 4.0,
    "I32": 4.0,
    "F16": 2.0,
    "BF16": 2.0,
    "U16": 2.0,
    "I16": 2.0,
    "F8": 1.0,
    "E4M3": 1.0,
    "E5M2": 1.0,
    "F8_E4M3": 1.0,
    "F8_E5M2": 1.0,
    "I8": 1.0,
    "U8": 1.0,
    "BOOL": 1.0,
    "F4": 0.5,
    "MXFP4": 0.5,
    "I4": 0.5,
    "U4": 0.5,
    "Q4_0": 0.5,
}

_PLAIN_DTYPES = {"float32": "F32", "float16": "F16", "bfloat16": "BF16", "float8": "F8"}


def dtype_bytes(dtype: str) -> float | None:
    return _DTYPE_BYTES.get(dtype.upper())


def _model_type_dtype(model_type: str) -> str | None:
    return _PLAIN_DTYPES.get(model_type)


def _read_safetensors_header(path: Path) -> tuple[dict[str, object], InspectionIssue | None]:
    """Read the JSON header of a .safetensors file without loading tensors."""
    try:
        with path.open("rb") as fh:
            raw_len = fh.read(8)
            if len(raw_len) < 8:
                return {}, InspectionIssue(level="error", message=f"{path.name}: truncated header")
            length = struct.unpack("<Q", raw_len)[0]
            if length > 64 * 1024 * 1024:  # sanity cap on header size
                return {}, InspectionIssue(
                    level="error", message=f"{path.name}: implausible header"
                )
            raw = fh.read(length)
            header = json.loads(raw)
            return (header if isinstance(header, dict) else {}, None)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, InspectionIssue(level="error", message=f"{path.name}: {exc}")


# Lightweight tensor-role heuristic mirroring the model-atlas classifier, so we
# can report achieved bits-per-weight per role (mixed-precision allocation data).
def _role_of(name: str) -> str:
    low = name.lower()
    if "embed" in low or "embed_tokens" in low:
        return "embedding"
    if "lm_head" in low or "eh_proj" in low:
        return "lm_head"
    if "router" in low or "gate.weight" in low or ".gate." in low:
        return "router"
    if "shared" in low:
        return "shared_expert"
    if ".experts." in low or "expert" in low:
        return "experts"
    if "attention" in low or "self_attn" in low or "kda" in low or "mla" in low:
        return "attention"
    if "latent" in low or "proj" in low:
        return "latent_proj"
    if "norm" in low:
        return "norm"
    return "other"


def _scan_safetensors(
    shards: list[Path],
) -> tuple[int, int, dict[str, float], dict[str, dict[str, float]], list[InspectionIssue]]:
    """Return (total_bytes, params, per_dtype bytes, per_role{bytes,numel}, issues)."""
    total = 0
    params = 0
    per_dtype: dict[str, float] = {}
    role: dict[str, dict[str, float]] = {}
    issues: list[InspectionIssue] = []
    for shard in shards:
        header, err = _read_safetensors_header(shard)
        total += shard.stat().st_size
        if err is not None:
            issues.append(err)
            continue
        for key, meta in header.items():
            if key == "__metadata__" or not isinstance(meta, dict):
                continue
            dtype = str(meta.get("dtype", ""))
            shape = meta.get("shape")
            offsets = meta.get("data_offsets")
            if not isinstance(shape, list):
                continue
            numel = math.prod(int(s) for s in shape)
            bytes_per = dtype_bytes(dtype)
            if bytes_per is None:
                # Unknown dtype counts as 4-byte conservative fill and is noted.
                bytes_per = 4.0
                issues.append(
                    InspectionIssue(
                        level="warning", message=f"{shard.name}: {key}: unknown dtype {dtype}"
                    )
                )
            per_dtype[dtype.upper()] = per_dtype.get(dtype.upper(), 0.0) + numel * bytes_per
            # real stored bytes from the header offsets when present
            if isinstance(offsets, list) and len(offsets) == 2:
                tbytes = float(offsets[1] - offsets[0])
            else:
                tbytes = float(numel * bytes_per)
            r = role.setdefault(_role_of(key), {"bytes": 0.0, "numel": 0.0})
            r["bytes"] += tbytes
            r["numel"] += numel
            params += numel
    return total, params, per_dtype, role, issues


def inspect_checkpoint(path: str | Path, *, memory_gb: float = 256.0) -> CheckpointInspection:
    """Classify a checkpoint directory without loading tensor payloads."""
    root = Path(path)
    issues: list[InspectionIssue] = []

    if not root.is_dir():
        return CheckpointInspection(
            path=str(root),
            valid=False,
            issues=[InspectionIssue(level="error", message="not a directory")],
        )

    config = {}
    config_path = root / "config.json"
    model_type = architecture = None
    num_layers = num_experts = top_k = None
    quant = None
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(InspectionIssue(level="error", message=f"config.json unreadable: {exc}"))
        if isinstance(config, dict):
            model_type = config.get("model_type")
            architecture = config.get("architectures")
            if isinstance(architecture, list) and architecture:
                architecture = architecture[0]
            inner = config.get("model_config")
            model_config: dict[str, Any] = inner if isinstance(inner, dict) else config
            num_layers = model_config.get("num_hidden_layers")
            num_experts = model_config.get("num_local_experts") or model_config.get("num_experts")
            top_k = model_config.get("num_experts_per_tok")
            qc = config.get("quantization_config")
            if isinstance(qc, dict):
                quant = qc.get("quant_method") or qc.get("quantization_method") or qc.get("format")
            if quant is None:
                inner_qc = model_config.get("quantization_config")
                if isinstance(inner_qc, dict):
                    quant = inner_qc.get("quant_method")
    else:
        issues.append(InspectionIssue(level="error", message="config.json not found"))

    shards = sorted(
        p for p in root.glob("*.safetensors") if not p.name.startswith("._")
    )
    total_bytes, params, per_dtype, role_bytes, shard_issues = _scan_safetensors(shards)
    issues.extend(shard_issues)
    precision_roles: list[dict[str, object]] = []
    for role, acc in sorted(role_bytes.items()):
        bpw = (acc["bytes"] * 8 / acc["numel"]) if acc["numel"] else None
        precision_roles.append(
            {
                "role": role,
                "stored_bytes": round(acc["bytes"]),
                "numel": round(acc["numel"]),
                "achieved_bpw": round(bpw, 2) if bpw is not None else None,
            }
        )
    shard_count = len(shards)

    # Fall back to unsplit weights for byte counting when no safetensors present.
    if total_bytes == 0:
        total_bytes = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
        if not shards:
            issues.append(
                InspectionIssue(level="warning", message="no safetensors shards found under root")
            )

    # Resolve dtype from the most common header dtype, else config dtype.
    tensor_dtype = (
        max(per_dtype, key=lambda k: per_dtype[k])
        if per_dtype
        else _model_type_dtype(model_type or "")
    )
    resident_est = int(sum(per_dtype.values())) if per_dtype else None

    # Atlas compatibility: layerwise MOE requires a recognized sparse config.
    atlas_compatible = bool(
        config and num_layers is not None and num_experts is not None and shard_count > 0
    )
    is_sparse = bool(num_experts)
    runnable_here = False
    if shard_count == 0:
        issues.append(InspectionIssue(level="error", message="tensor shards not resolvable"))
    if atlas_compatible and not is_sparse:
        issues.append(
            InspectionIssue(
                level="warning",
                message=f"detected {num_layers} layers but no routed (MOE) experts",
            )
        )
    if resident_est is not None:
        mem_gb = resident_est / (1024**3)
        runnable_here = mem_gb <= max(memory_gb - 8.0, 0.0) and bool(config)

    return CheckpointInspection(
        path=str(root),
        valid=bool(config) and shard_count > 0,
        model_type=model_type,
        architecture=architecture,
        num_hidden_layers=num_layers,
        num_local_experts=num_experts,
        num_experts_per_tok=top_k,
        quantization_format=quant,
        tensor_dtype=tensor_dtype,
        file_count=sum(1 for _ in root.rglob("*") if _.is_file()),
        shard_count=shard_count if isinstance(shard_count, int) else len(shards),
        stored_size_bytes=total_bytes,
        params_estimate=params,
        resident_estimate_bytes=resident_est,
        runnable_here=runnable_here,
        atlas_compatible=atlas_compatible,
        issues=issues,
        precision_roles=precision_roles,
    )
