#!/usr/bin/env python3
"""Extract selected workflow GEN target phi kinematics from six merged samples."""
import argparse
from itertools import zip_longest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

SAMPLES = ("JJP_DPS1", "JJP_DPS2_CS", "JJP_DPS2_G", "JJP_SPS_CS", "JJP_SPS_G", "JJP_TPS")
KEYS = ("sample", "source_file", "entry", "run", "lumi", "event")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    schema = pa.schema([("sample", pa.string()), ("population", pa.string()),
                        ("phi_abs_y", pa.float64())])
    writer = pq.ParquetWriter(args.output, schema)
    try:
        for sample in SAMPLES:
            root = args.merged_dir / sample
            gen = pq.ParquetFile(root / "gen_systems.parquet")
            flags = pq.ParquetFile(root / "event_step_flags.parquet")
            gcols = [*KEYS, "phi_abs_y"]
            fcols = [*KEYS, "full_gen"]
            for g, f in zip_longest(gen.iter_batches(batch_size=100_000, columns=gcols),
                                    flags.iter_batches(batch_size=100_000, columns=fcols)):
                if g is None or f is None:
                    raise RuntimeError(f"GEN/flag batch mismatch in {sample}")
                gd, fd = g.to_pydict(), f.to_pydict()
                if any(gd[key] != fd[key] for key in KEYS):
                    raise RuntimeError(f"GEN/flag key mismatch in {sample}")
                keep = [i for i, yes in enumerate(fd["full_gen"]) if yes]
                if not keep:
                    continue
                writer.write_table(pa.Table.from_pydict({
                    "sample": [sample] * len(keep),
                    "population": ["workflow_target_GEN_full_gen"] * len(keep),
                    "phi_abs_y": [float(gd["phi_abs_y"][i]) for i in keep],
                }, schema=schema))
    finally:
        writer.close()


if __name__ == "__main__":
    main()
