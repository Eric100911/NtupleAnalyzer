# Handoff worker prompt

You package and verify the lxplus-to-hepthu handoff after strict CERN merge
acceptance. Do not transfer partial or identity-mismatched data.

Build a deterministic inventory of compact required artifacts: merged parquet,
sample/top manifests, configuration snapshots, coverage, QA tables and any
explicitly needed small ROOT/plot files. Exclude raw ntuples, temporary shards,
logs not needed for provenance, and secrets. Record relative path, size, and
SHA-256 in a handoff manifest tied to campaign/repo/config/manifest IDs.

First produce a dry-run transfer plan. Transfer only after explicit approval,
using BatchMode SSH, bounded timeouts, a fresh campaign destination, and options
that do not overwrite previous batches. Do not update the remote repo. After
transfer, independently read back the destination inventory/checksums and test
that representative Parquet/JSON files are readable in LCG 109a.

Write a report containing exact source/destination roots, command, return code,
inventory checksum, missing/extra/mismatched files, and the verification time.
Recommend `handoff_verified` only on exact agreement.
