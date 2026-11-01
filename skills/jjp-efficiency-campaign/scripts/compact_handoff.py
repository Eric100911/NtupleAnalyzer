#!/usr/bin/env python3
"""Build and verify one local, compact JJP efficiency tar.gz handoff.

No network or batch-system operations are implemented. The sidecar manifest is
readable metadata (member names and sizes); the tarball has one whole-bundle
SHA-256. Raw ROOT files, shards, logs, and path traversal are rejected.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, tarfile, tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

SCHEMA = "jjp-efficiency-compact-handoff/v3"
MANIFEST_NAME = "compact-handoff-manifest.json"
REQUIRED_MEMBERS = {
    "formal_merge_report.json", "sample_manifest.json", "manifest.json",
    "configuration_metadata.json", "file_coverage.parquet", "gen_systems.parquet",
    "event_step_flags.parquet", "efficiency_maps.parquet", "efficiency_counts.parquet",
}
OPTIONAL_QA_MEMBERS = {
    "cutflow.csv", "four_muon_definition_comparison.csv", "gen_ancestry_qa.parquet",
    "subprocess_summary.csv", "subprocess_summary.parquet", "subprocess_envelope.parquet",
}
FORBIDDEN_PARTS = {"raw", "raw-ntuples", "ntuple", "ntuples", "shard", "shards",
                   "tmp", "temp", "log", "logs", "secret", "secrets", ".ssh",
                   "proxy", "proxies"}
MAX_QA_BYTES = 25 * 1024 * 1024
SAMPLE_RE = re.compile(r"JJP_[A-Za-z0-9_]+$")
SHA256_RE = re.compile(r"[0-9a-fA-F]{64}$")
GIT_SHA_RE = re.compile(r"[0-9a-fA-F]{40,64}$")
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9_.:@+-]+$")
QA_NAME_RE = re.compile(r"(?:qa|cutflow|comparison|summary|coverage)", re.IGNORECASE)

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def _hex(value: Any, field: str, *, git=False) -> str:
    text = str(value or "")
    if not (GIT_SHA_RE if git else SHA256_RE).fullmatch(text):
        kind = "40-64 character Git SHA" if git else "64-character SHA-256"
        raise ValueError(f"{field} must be a {kind}")
    return text.lower()

def _identifier(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text or not IDENTIFIER_RE.fullmatch(text):
        raise ValueError(f"{field} must be a non-empty identifier")
    return text

def safe_member(raw: str) -> PurePosixPath:
    """Allow only canonical, root-level regular-file names."""
    if not isinstance(raw, str) or not raw:
        raise ValueError("empty handoff member name")
    if "\\" in raw:
        raise ValueError(f"unsafe handoff member path: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or len(path.parts) != 1 or path.parts[0] in {"", ".", ".."}:
        raise ValueError(f"unsafe handoff member path: {raw!r}")
    if path.as_posix() != raw:
        raise ValueError(f"handoff member path is not canonical POSIX syntax: {raw!r}")
    if path.name.lower().endswith((".root", ".log")):
        raise ValueError(f"ROOT/log files are not allowed in a compact handoff: {raw}")
    if any(part.lower() in FORBIDDEN_PARTS for part in path.parts):
        raise ValueError(f"forbidden handoff member path: {raw}")
    return path

def _source_file(root: Path, name: str) -> Path:
    path = root / safe_member(name).name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"handoff member is not a regular source file: {name}")
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise ValueError(f"handoff member escapes source root: {name}") from exc
    return path

def _json_object(path: Path, name: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read {name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be a JSON object")
    return payload

def _required_evidence(root: Path, sample: str) -> None:
    report = _json_object(_source_file(root, "formal_merge_report.json"), "formal_merge_report.json")
    if report.get("sample") != sample or report.get("passed") is not True:
        raise ValueError("formal_merge_report.json must be passed for the requested sample")
    coverage = report.get("coverage")
    if not isinstance(coverage, dict) or coverage.get("complete") is not True:
        raise ValueError("formal_merge_report.json must prove complete coverage")
    sm = _json_object(_source_file(root, "sample_manifest.json"), "sample_manifest.json")
    if sm.get("sample") != sample:
        raise ValueError("sample_manifest.json sample does not match the requested sample")
    manifest = _json_object(_source_file(root, "manifest.json"), "manifest.json")
    if manifest.get("sample") not in (None, sample):
        raise ValueError("manifest.json sample does not match the requested sample")
    _json_object(_source_file(root, "configuration_metadata.json"), "configuration_metadata.json")

def _member_names(root: Path, include: Iterable[str] | None) -> list[str]:
    requested = list(include or [])
    if len(set(requested)) != len(requested):
        raise ValueError("duplicate --include member")
    # Required products are always present; --include only adds named QA.
    names = set(REQUIRED_MEMBERS) | set(requested)
    missing = REQUIRED_MEMBERS - names
    if missing:
        raise ValueError("handoff is missing required merged products: " + ", ".join(sorted(missing)))
    for name in names:
        safe_member(name)
        optional = name not in REQUIRED_MEMBERS
        if optional and (name not in OPTIONAL_QA_MEMBERS
                         and (Path(name).suffix.lower() not in {".csv", ".parquet"}
                              or not QA_NAME_RE.search(name))):
            raise ValueError(f"unsupported compact-handoff member: {name}")
    if not requested:
        names.update(name for name in OPTIONAL_QA_MEMBERS if (root / name).is_file())
    return sorted(names)

def _metadata(sample: str, campaign_id: str, repo_sha: str, formal_manifest_id: str,
              yaml_sha256: str, runtime_tarball_sha256: str) -> dict[str, str]:
    if not SAMPLE_RE.fullmatch(sample):
        raise ValueError("sample must be a JJP efficiency sample label")
    return {"campaign_id": _identifier(campaign_id, "campaign_id"),
            "repo_sha": _hex(repo_sha, "repo_sha", git=True),
            "formal_manifest_id": _identifier(formal_manifest_id, "formal_manifest_id"),
            "yaml_sha256": _hex(yaml_sha256, "yaml_sha256"),
            "runtime_tarball_sha256": _hex(runtime_tarball_sha256, "runtime_tarball_sha256"),
            "sample": sample}

def _write_new_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing handoff manifest: {path}")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True); handle.write("\n")
            handle.flush(); os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)

def build_bundle(source_root: Path, output_bundle: Path, *, sample: str, campaign_id: str,
                 repo_sha: str, formal_manifest_id: str, yaml_sha256: str,
                 runtime_tarball_sha256: str, include: Iterable[str] | None = None,
                 write_manifest: Path | None = None) -> dict[str, Any]:
    """Build one tarball and sidecar manifest. Existing destinations are refused."""
    root = Path(source_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"source root is not a directory: {root}")
    output = Path(output_bundle)
    if not output.name.endswith((".tar.gz", ".tgz")):
        raise ValueError("output bundle must have a .tar.gz filename")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing handoff bundle: {output}")
    manifest_path = Path(write_manifest) if write_manifest else Path(str(output) + ".manifest.json")
    if manifest_path.exists():
        raise FileExistsError(f"refusing to overwrite existing handoff manifest: {manifest_path}")
    names = _member_names(root, include); _required_evidence(root, sample)
    sources = {name: _source_file(root, name) for name in names}
    for name, path in sources.items():
        if name not in REQUIRED_MEMBERS and path.stat().st_size > MAX_QA_BYTES:
            raise ValueError(f"optional QA member is too large: {name}")
    metadata = _metadata(sample, campaign_id, repo_sha, formal_manifest_id, yaml_sha256,
                         runtime_tarball_sha256)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent); os.close(fd)
    temporary = Path(temporary)
    try:
        with tarfile.open(temporary, "w:gz") as archive:
            for name in names:
                info = archive.gettarinfo(str(sources[name]), arcname=name)
                info.uid = info.gid = 0; info.uname = info.gname = ""
                with sources[name].open("rb") as handle: archive.addfile(info, handle)
        digest = file_sha256(temporary)
        manifest = {"schema_version": SCHEMA, "bundle_kind": "compact-tar-gz",
                    "created_at": utc_now(), "sample": sample, "metadata": metadata,
                    "bundle": {"filename": output.name, "size": temporary.stat().st_size,
                               "sha256": digest},
                    "members": [{"path": n, "size": sources[n].stat().st_size} for n in names]}
        os.link(temporary, output)
        _write_new_json(manifest_path, manifest)
        return manifest
    finally:
        temporary.unlink(missing_ok=True)

def validate_manifest(manifest: dict[str, Any]) -> None:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA:
        raise ValueError("unexpected compact-handoff manifest schema")
    if manifest.get("bundle_kind") != "compact-tar-gz":
        raise ValueError("manifest is not a compact tar.gz handoff")
    sample = manifest.get("sample")
    if not isinstance(sample, str) or not SAMPLE_RE.fullmatch(sample): raise ValueError("invalid handoff sample")
    metadata = manifest.get("metadata")
    fields = {"campaign_id", "repo_sha", "formal_manifest_id", "yaml_sha256", "runtime_tarball_sha256", "sample"}
    if not isinstance(metadata, dict) or set(metadata) != fields or metadata.get("sample") != sample:
        raise ValueError("handoff metadata is incomplete")
    _identifier(metadata["campaign_id"], "campaign_id"); _hex(metadata["repo_sha"], "repo_sha", git=True)
    _identifier(metadata["formal_manifest_id"], "formal_manifest_id"); _hex(metadata["yaml_sha256"], "yaml_sha256")
    _hex(metadata["runtime_tarball_sha256"], "runtime_tarball_sha256")
    bundle = manifest.get("bundle")
    if not isinstance(bundle, dict) or set(bundle) != {"filename", "size", "sha256"}:
        raise ValueError("handoff bundle evidence is incomplete")
    safe_member(bundle["filename"])
    if not str(bundle["filename"]).endswith((".tar.gz", ".tgz")): raise ValueError("handoff bundle filename must be tar.gz")
    if isinstance(bundle["size"], bool) or not isinstance(bundle["size"], int) or bundle["size"] < 1: raise ValueError("invalid handoff bundle size")
    _hex(bundle["sha256"], "bundle.sha256")
    members = manifest.get("members")
    if not isinstance(members, list) or not members: raise ValueError("handoff manifest has no member list")
    paths = []
    for row in members:
        if not isinstance(row, dict) or set(row) != {"path", "size"}: raise ValueError("member rows contain paths and sizes only")
        safe_member(row["path"])
        if isinstance(row["size"], bool) or not isinstance(row["size"], int) or row["size"] < 0: raise ValueError("invalid handoff member size")
        paths.append(row["path"])
    if paths != sorted(set(paths)): raise ValueError("handoff member list must be sorted and unique")
    if not REQUIRED_MEMBERS.issubset(paths): raise ValueError("handoff member list omits required merged products")
    for path in paths:
        if path not in REQUIRED_MEMBERS and (path not in OPTIONAL_QA_MEMBERS
                and (Path(path).suffix.lower() not in {".csv", ".parquet"} or not QA_NAME_RE.search(path))):
            raise ValueError("unsupported handoff member")

def load_manifest(path: Path) -> dict[str, Any]:
    try: payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise ValueError(f"unable to read handoff manifest: {exc}") from exc
    validate_manifest(payload); return payload

def _tar_members(bundle: Path) -> dict[str, tarfile.TarInfo]:
    try:
        with tarfile.open(bundle, "r:gz") as archive: rows = archive.getmembers()
    except (OSError, tarfile.TarError) as exc: raise ValueError(f"unable to read handoff tarball: {exc}") from exc
    found = {}
    for member in rows:
        path = safe_member(member.name)
        if not member.isfile(): raise ValueError(f"handoff tarball contains non-regular member: {member.name}")
        if path.name in found: raise ValueError(f"handoff tarball contains duplicate member: {member.name}")
        found[path.name] = member
    return found

def verify_bundle(bundle: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest); path = Path(bundle).resolve(strict=True)
    expected = manifest["bundle"]; digest = file_sha256(path); members = _tar_members(path)
    filename_ok = path.name == expected["filename"]
    sizes = {r["path"]: r["size"] for r in manifest["members"]}; actual = set(members)
    missing = sorted(set(sizes) - actual); extra = sorted(actual - set(sizes))
    bad_sizes = sorted(n for n in sizes if n in members and members[n].size != sizes[n])
    verified = (filename_ok and digest == expected["sha256"] and path.stat().st_size == expected["size"]
                and not missing and not extra and not bad_sizes)
    return {"operation": "compact-handoff-verify", "bundle": str(path), "sample": manifest["sample"],
            "bundle_sha256": digest, "expected_bundle_sha256": expected["sha256"],
            "size": path.stat().st_size, "expected_size": expected["size"], "missing": missing,
            "extra": extra, "member_size_mismatches": bad_sizes, "verified": verified, "verified_at": utc_now()}

def _verify_extracted(root: Path, manifest: dict[str, Any]) -> bool:
    expected = {r["path"]: r["size"] for r in manifest["members"]}
    actual = {p.name: p.stat().st_size for p in root.iterdir() if p.is_file() and not p.is_symlink() and p.name != MANIFEST_NAME}
    return actual == expected

def extract_bundle(bundle: Path, destination_root: Path, manifest: dict[str, Any], *, write_manifest=True) -> dict[str, Any]:
    check = verify_bundle(bundle, manifest)
    if not check["verified"]: raise ValueError(f"handoff bundle verification failed: {check}")
    destination = Path(destination_root)
    if destination.exists(): raise FileExistsError(f"refusing to use existing extraction destination: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True); destination.mkdir()
    try:
        with tarfile.open(Path(bundle), "r:gz") as archive:
            for member in archive.getmembers():
                target = destination / safe_member(member.name).name; source = archive.extractfile(member)
                if source is None: raise ValueError(f"unable to extract handoff member: {member.name}")
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024); output.flush(); os.fsync(output.fileno())
        if write_manifest: _write_new_json(destination / MANIFEST_NAME, manifest)
    except Exception: raise
    if not _verify_extracted(destination, manifest): raise ValueError("extracted handoff does not match member names and sizes")
    return {"operation": "compact-handoff-extract", "destination": str(destination.resolve()), "sample": manifest["sample"], "bundle_sha256": manifest["bundle"]["sha256"], "verified": True, "verified_at": utc_now()}

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build one compact tar.gz handoff")
    build.add_argument("--source-root", type=Path, required=True); build.add_argument("--output-bundle", "--bundle", type=Path, required=True)
    build.add_argument("--sample", required=True); build.add_argument("--campaign-id", required=True); build.add_argument("--repo-sha", required=True)
    build.add_argument("--formal-manifest-id", required=True); build.add_argument("--yaml-sha256", "--yaml-sha", "--efficiency-config-sha256", dest="yaml_sha256", required=True)
    build.add_argument("--runtime-tarball-sha256", "--runtime-tar-sha256", "--runtime-sha256", dest="runtime_tarball_sha256", required=True)
    build.add_argument("--include", action="append", default=[]); build.add_argument("--write-manifest", type=Path)
    for name in ("verify", "extract"):
        sub = commands.add_parser(name); sub.add_argument("--bundle", type=Path, required=True); sub.add_argument("--manifest", type=Path)
        if name == "extract": sub.add_argument("--destination-root", type=Path, required=True)
    return parser

def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            result = build_bundle(args.source_root, args.output_bundle, sample=args.sample, campaign_id=args.campaign_id, repo_sha=args.repo_sha, formal_manifest_id=args.formal_manifest_id, yaml_sha256=args.yaml_sha256, runtime_tarball_sha256=args.runtime_tarball_sha256, include=args.include or None, write_manifest=args.write_manifest)
        else:
            manifest = load_manifest(args.manifest or Path(str(args.bundle) + ".manifest.json"))
            result = verify_bundle(args.bundle, manifest) if args.command == "verify" else extract_bundle(args.bundle, args.destination_root, manifest)
            if args.command == "verify" and not result["verified"]:
                print(json.dumps(result, indent=2, sort_keys=True)); return 2
        print(json.dumps(result, indent=2, sort_keys=True)); return 0
    except (OSError, ValueError, tarfile.TarError, FileExistsError) as exc:
        print(f"compact_handoff.py: {exc}", file=os.sys.stderr); return 2

if __name__ == "__main__": raise SystemExit(main())
