from __future__ import annotations

import json
import hashlib
from pathlib import Path


def throw_factorized_maps(
    nominal_sample_dir: str | Path,
    toy_sample_dir: str | Path,
    *,
    rng,
    clip: tuple[float, float] = (1e-6, 1.0),
) -> dict[str, Path]:
    """Write one toy copy of all factorized-map parquet files for a sample."""
    import pandas as pd

    nominal_sample_dir = Path(nominal_sample_dir)
    toy_sample_dir = Path(toy_sample_dir)
    nominal_maps_dir = nominal_sample_dir / "maps"
    toy_maps_dir = toy_sample_dir / "maps"
    if not nominal_maps_dir.exists():
        raise FileNotFoundError(f"Nominal maps directory not found: {nominal_maps_dir}")

    toy_maps_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for map_path in sorted(nominal_maps_dir.glob("*.parquet")):
        if map_path.name == "manifest.parquet":
            continue
        frame = pd.read_parquet(map_path)
        thrown = throw_efficiency_frame(frame, rng=rng, clip=clip)
        output_path = toy_maps_dir / map_path.name
        thrown.to_parquet(output_path, index=False)
        written[map_path.stem] = output_path

    if not written:
        raise FileNotFoundError(f"No map parquet files found in {nominal_maps_dir}")

    manifest = {
        "stage": "mc_stat_toy_maps",
        "source": str(nominal_maps_dir.resolve()),
        "maps": {name: path.name for name, path in written.items()},
        "clip": [float(clip[0]), float(clip[1])],
    }
    (toy_maps_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return written


def throw_efficiency_frame(
    frame,
    *,
    rng,
    clip: tuple[float, float] = (1e-6, 1.0),
):
    """Throw the efficiency column within err_sym, preserving metadata columns."""
    import numpy as np
    import pandas as pd

    if "efficiency" not in frame.columns:
        return frame.copy()

    thrown = frame.copy()
    efficiency = pd.to_numeric(thrown["efficiency"], errors="coerce").to_numpy(dtype=float)
    if "err_sym" in thrown.columns:
        err_sym = pd.to_numeric(thrown["err_sym"], errors="coerce").to_numpy(dtype=float)
    else:
        err_sym = np.zeros(len(thrown), dtype=float)

    mask = np.isfinite(efficiency) & np.isfinite(err_sym) & (err_sym > 0.0)
    varied = efficiency.copy()
    if np.any(mask):
        varied[mask] = rng.normal(efficiency[mask], err_sym[mask])
    finite = np.isfinite(varied)
    varied[finite] = np.clip(varied[finite], float(clip[0]), float(clip[1]))
    thrown["efficiency"] = varied
    return thrown


def toy_seed(base_seed: int, toy_index: int, sample: str) -> int:
    """Derive a stable 32-bit seed for one toy/sample pair."""
    payload = f"{int(base_seed)}:{int(toy_index)}:{sample}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "little", signed=False)
