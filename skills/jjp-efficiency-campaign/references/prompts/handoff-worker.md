# Handoff worker prompt

Package and locally verify the handoff after strict CERN merge acceptance. This
worker has no network, SSH, transfer, Condor, scheduler, or remote-repository
operations.

Use `scripts/compact_handoff.py` to create exactly one compact `.tar.gz` per
sample. The source must contain the required merged products and a
`formal_merge_report.json` with the requested sample, `passed: true`, and
`coverage.complete: true`. Include the sample/product manifests,
configuration metadata, file coverage, GEN/event tables, efficiency maps and
counts, plus only small known QA CSV/Parquet tables. ROOT files, shards, logs,
arbitrary files, symlinks, and path-traversal names are rejected.

Pass campaign ID, repository SHA, formal manifest ID, efficiency-YAML SHA, and
runtime-tarball SHA as metadata. The sidecar manifest is readable and records
member names/sizes; it must not contain per-file cryptographic hashes. Verify
using the single whole-bundle SHA-256, then extract only to a fresh destination.
Existing bundle, manifest, or extraction paths are never overwritten or
cleaned. Recommend `handoff_verified` only after local archive and extraction
verification succeeds.
