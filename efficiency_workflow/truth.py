from __future__ import annotations

from typing import Any


def to_int_idx(value: Any, default: int = -1) -> int:
    if value is None:
        return default
    try:
        return int(round(float(value)))
    except Exception:
        return default


def first_ancestor_idx(
    gen_pdg: list[int],
    gen_mother_idx: list[int],
    start_idx: Any,
    target_abs_pdg: int | tuple[int, ...] | list[int] | set[int],
) -> int:
    target_abs_pdgs = {abs(int(target_abs_pdg))} if isinstance(target_abs_pdg, int) else {abs(int(value)) for value in target_abs_pdg}
    idx = to_int_idx(start_idx, -1)
    seen: set[int] = set()
    while 0 <= idx < len(gen_pdg) and idx not in seen:
        seen.add(idx)
        if abs(int(gen_pdg[idx])) in target_abs_pdgs:
            return idx
        idx = to_int_idx(gen_mother_idx[idx], -1)
    return -1
