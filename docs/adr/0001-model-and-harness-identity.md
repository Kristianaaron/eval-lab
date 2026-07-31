# ADR-0001: Model and harness identity are separate

Status: Accepted  
Date: 2026-07-31  
Decision: `ModelConfig` and `HarnessConfig` are distinct, independently
versioned schema objects. A `RunManifest` may reference either or both, but a
run is never identified by "the model" alone.

## Context

The spec (4.6, 4.8) states that the same checkpoint under two agent loops is two
different evaluated systems, and that every result must identify the full
evaluation configuration (6.4). Collapsing "model" and "harness" into a single
identity would let a harness regression masquerade as a model improvement, or
vice versa — exactly what the platform exists to detect (spec 27: harness design
materially affects agent results).

## Decision

- `ModelConfig` captures provider, endpoint, checkpoint, quantization, runtime,
  sampling, capabilities — the answer to "which weights, served how".
- `HarnessConfig` captures agent loop, system prompt, workspace policy, context
  policy, recovery policy, completion contract, tool adapter version — the
  answer to "which agent machinery wraps those weights".
- `RunManifest` carries `model_id` and `harness_id` as separate optional fields,
  so a run can be direct (model, no harness) or system (model + harness).

## Consequences

- Comparing a K3 student across two keep-maps requires only changing `ModelConfig`;
  comparing two agent loops requires only changing `HarnessConfig`. Neither
  change invalidates the other object's versioning.
- Direct and system runs cannot be silently merged (spec 2) because level and
  harness identity are retained distinctly.
- Cost: a run manifest is slightly larger and callers must know which identity
  changed. Worth it — this is the core regression-detection contract.

## Alternatives considered

- Single "configuration" blob: rejected — cannot isolate harness vs model effect.
- Free-text tags: rejected — violates reproducible-identity requirement.
