You are given the complete source listing of a small Python library, `flowkit`, as an attachment. Every file is included, each introduced by a `===== FILE: <path> =====` header. The library's behavioural contract is documented in its `README.md`.

The nightly reporting job that uses `flowkit.aggregate.summarize` has been producing wrong numbers. Two symptoms were reported by the data team:

1. For a sample of 30 latency values, the reported `p95` is the 28th smallest value; the team expected the 29th.
2. For a sample of 20 values `1, 2, ..., 20`, the reported `median` is `11`; the team expected `10.5`.

Exactly one source file contains the defect(s). Using only the attached listing:

- Identify the file, and explain in one or two sentences what is wrong with respect to the documented contract.
- Then output the **complete corrected contents of that one file** as a single fenced ```python block. The block must be a drop-in replacement (same module path, same public names and signatures); do not change the behaviour of anything that is not defective and do not reference modules that do not exist in the listing.

Reply with the explanation followed by exactly one fenced ```python block.
