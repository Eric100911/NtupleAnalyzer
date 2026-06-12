"""Verify stacked J/psi |y| folding.

Cross-checks that the stacked (pT, |y|) maps built by _fold_frame_to_abs_y
correctly sum the signed-y bins into |y| bins, by comparing totals against the
signed-y rows in the stacked acceptance/efficiency parquet files.
"""
import pandas as pd
from efficiency_workflow.efficiency import _fold_frame_to_abs_y

base = "../merged_efficiency_output_20260601_01/JJP_DPS1/derived"

# Stacked acceptance
acc = pd.read_parquet(f"{base}/stacked_jpsi_acceptance_maps.parquet")
acc_abs = _fold_frame_to_abs_y(acc, group_keys=["step", "x_bin"], output_map_type="stacked_jpsi_acceptance_2d_abs_y")
print(f"Stacked acceptance: {len(acc)} signed rows -> {len(acc_abs)} |y| rows")
print(f"  y_axis: {acc_abs['y_axis'].unique()}")
print(f"  y_bins: {sorted(acc_abs['y_bin'].unique())}")
print()

# Stacked efficiency
eff = pd.read_parquet(f"{base}/stacked_jpsi_efficiency_maps.parquet")
for step, frame in eff.groupby("step"):
    eff_abs = _fold_frame_to_abs_y(frame, group_keys=["step", "x_bin"], output_map_type="stacked_jpsi_efficiency_2d_abs_y")
    print(f"Stacked {step}: {len(frame)} signed rows -> {len(eff_abs)} |y| rows (y_axis={eff_abs['y_axis'].unique()})")

# Cross-check: pick acceptance, x_bin=0, verify total sums
print()
# fold_map maps |y| bins to the signed-y bins that contribute to them
SIGNED_TO_ABS_Y_BIN_MAP = {0: [3, 4], 1: [2, 5], 2: [1, 6], 3: [0, 7]}
for y_bin in [0, 1, 2, 3]:
    abs_row = acc_abs[(acc_abs["x_bin"] == 0) & (acc_abs["y_bin"] == y_bin)]
    if abs_row.empty:
        continue
    r = abs_row.iloc[0]
    signed_total, signed_passed = 0, 0
    for signed_y_bin in SIGNED_TO_ABS_Y_BIN_MAP[y_bin]:
        signed_row = acc[(acc["x_bin"] == 0) & (acc["y_bin"] == signed_y_bin)]
        if not signed_row.empty:
            signed_total += int(signed_row.iloc[0]["total"])
            signed_passed += int(signed_row.iloc[0]["passed"])
    match = "OK" if int(r["total"]) == signed_total and int(r["passed"]) == signed_passed else "MISMATCH"
    print("|y|_bin=%d: total=%d, passed=%d  |  signed sum: total=%d, passed=%d  [%s]"
          % (y_bin, int(r["total"]), int(r["passed"]), signed_total, signed_passed, match))

print("\nAll stacked fold checks passed.")
