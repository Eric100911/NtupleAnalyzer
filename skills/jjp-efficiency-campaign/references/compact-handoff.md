# Compact per-sample handoff

`scripts/compact_handoff.py` creates a local, create-only handoff for one
merged JJP sample. It has no SSH, transfer, Condor, or scheduler code.

The output is one `tar.gz` plus a readable sidecar manifest. The tarball SHA-256
is the only cryptographic check. The sidecar records the campaign ID, repository
SHA, formal manifest ID, efficiency-YAML SHA-256, runtime-tarball SHA-256, and a
plain list of tar members with byte sizes. It intentionally does not repeat
per-file hashes or deep cross-validation already performed by the formal merge.

Build from a completed sample directory (the required files must all exist):

```bash
python3 skills/jjp-efficiency-campaign/scripts/compact_handoff.py build \
  --source-root /path/to/merged/JJP_DPS1 \
  --output-bundle /path/to/handoff/JJP_DPS1.tar.gz \
  --sample JJP_DPS1 --campaign-id campaign-01 \
  --repo-sha <git-sha> --formal-manifest-id <formal-id> \
  --yaml-sha256 <yaml-sha256> --runtime-tarball-sha256 <runtime-sha256>
```

The bundle requires `formal_merge_report.json` with `passed: true`, the requested
sample, and `coverage.complete: true`. It includes these merged products:
`sample_manifest.json`, `manifest.json`, `configuration_metadata.json`,
`file_coverage.parquet`, `gen_systems.parquet`, `event_step_flags.parquet`,
`efficiency_maps.parquet`, and `efficiency_counts.parquet`. Small known QA
products (`cutflow.csv`, `four_muon_definition_comparison.csv`,
`gen_ancestry_qa.parquet`, and summary tables) are included when present. Use
repeated `--include` to select optional QA members explicitly; required members
cannot be omitted. ROOT, shards, logs, arbitrary files, nested paths, and path
traversal are rejected.

Verify and extract only into fresh destinations:

```bash
python3 skills/jjp-efficiency-campaign/scripts/compact_handoff.py verify \
  --bundle /path/to/handoff/JJP_DPS1.tar.gz
python3 skills/jjp-efficiency-campaign/scripts/compact_handoff.py extract \
  --bundle /path/to/handoff/JJP_DPS1.tar.gz \
  --destination-root /path/to/fresh/JJP_DPS1
```

Both operations verify the whole-bundle SHA, reject unsafe/non-regular tar
members, and check the readable member list and sizes. Existing bundle,
manifest, or extraction destinations are never overwritten or cleaned. This
helper performs packaging and local verification only; it does not add network
transfer.
