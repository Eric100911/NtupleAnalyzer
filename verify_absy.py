"""Verify |y| folding correctness: cross-check totals against signed-y sums.

This script reads the object_2d efficiency maps (which use signed rapidity bins),
folds them to |y| via fold_object_2d_to_abs_y(), and then cross-checks that
the |y| bin totals match the sum of the signed-y bins that map to them.
"""
import pandas as pd
from efficiency_workflow.efficiency import fold_object_2d_to_abs_y

df = pd.read_parquet(
    "/home/storage29/users/chiwang/JpsiJpsiPhi/analysis/Efficiency/"
    "NtupleAnalyzer/../merged_efficiency_output_20260601_01/JJP_DPS1/efficiency_maps.parquet"
)
folded = fold_object_2d_to_abs_y(df)
abs_rows = folded[folded["map_type"] == "object_2d_abs_y"]
print("|y| rows:", len(abs_rows))
print("y_axis:", abs_rows["y_axis"].unique())
print("y_bins:", sorted(abs_rows["y_bin"].unique()))
print()

obj2d = df[df["map_type"] == "object_2d"]
# fold_map maps |y| bins to the signed-y bins that contribute to them
SIGNED_TO_ABS_Y_BIN_MAP = {0: [3, 4], 1: [2, 5], 2: [1, 6], 3: [0, 7]}
for y_bin in [0, 1, 2, 3]:
    mask = (
        (abs_rows["object"] == "jpsi_lead")
        & (abs_rows["step"] == "dimuon")
        & (abs_rows["x_bin"] == 0)
        & (abs_rows["y_bin"] == y_bin)
    )
    row = abs_rows[mask]
    if row.empty:
        continue
    abs_row = row.iloc[0]
    signed_total = 0
    signed_passed = 0
    for signed_y_bin in SIGNED_TO_ABS_Y_BIN_MAP[y_bin]:
        smask = (
            (obj2d["object"] == "jpsi_lead")
            & (obj2d["step"] == "dimuon")
            & (obj2d["x_bin"] == 0)
            & (obj2d["y_bin"] == signed_y_bin)
        )
        signed_row = obj2d[smask]
        if not signed_row.empty:
            signed_total += int(signed_row.iloc[0]["total"])
            signed_passed += int(signed_row.iloc[0]["passed"])
    match = (
        "OK"
        if int(abs_row["total"]) == signed_total and int(abs_row["passed"]) == signed_passed
        else "MISMATCH"
    )
    print(
        "|y|_bin=%d: total=%d, passed=%d  |  signed sum: total=%d, passed=%d  [%s]"
        % (y_bin, int(abs_row["total"]), int(abs_row["passed"]), signed_total, signed_passed, match)
    )

print()
counts = abs_rows.groupby(["object", "step"]).size()
print("Rows per (object, step) in |y| maps:")
print(counts.to_string())
