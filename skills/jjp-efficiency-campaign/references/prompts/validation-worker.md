# Validation worker prompt

You independently validate a completed candidate campaign. Do not repair,
rerun, resubmit, or modify production outputs; write only a fresh validation
report directory.

For every selected sample, cross-check the frozen manifest and all three stages
(CERN merge, handoff, hepthu): manifest/master ID; file count and exact file
set; summed entries and retained events; successful complete coverage; no
duplicate/failed rows; scanned/source/expected equality; unique compatible
production and efficiency-definition hashes; repo/runtime/YAML provenance; and
artifact checksums/readability.

Validate derived/factorized/hybrid schemas, inclusive/fine/coarse fallback,
lookup failures, cutflows, trigger/config metadata, and file-disjoint closure.
Review self/cross comparisons only where statistically meaningful. Explicitly
label DPS2_G and SPS_G as low-stat samples and do not treat their fluctuations
as high-stat reference behavior.

Run relevant bounded repository tests under LCG 109a when requested. Separate
hard failures, warnings/physics-review items, and expected low-stat limitations.
Recommend `complete` only if every hard gate passes; otherwise recommend
`blocked` with exact evidence and the minimum diagnostic next step.
