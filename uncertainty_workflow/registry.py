from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .config import SystematicSource, Variation
from .provenance import hash_config, write_manifest


@dataclass(frozen=True)
class VariationResult:
    source: str
    variation: str
    status: str
    target_value: float
    target_uncertainty: float
    artifacts: dict[str, Path]
    manifest_path: Path


Runner = Callable[[SystematicSource, Variation], VariationResult]


class SystematicRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, SystematicSource] = {}
        self._runners: dict[str, Runner] = {}

    def register(self, source: SystematicSource, runner: Runner | None = None) -> None:
        if source.name in self._sources:
            raise ValueError(f"duplicate systematic source: {source.name}")
        self._sources[source.name] = source
        if runner is not None:
            self._runners[source.name] = runner

    def set_runner(self, source_name: str, runner: Runner) -> None:
        if source_name not in self._sources:
            raise KeyError(f"unknown systematic source: {source_name}")
        self._runners[source_name] = runner

    def list_sources(self) -> list[str]:
        return sorted(self._sources)

    def get(self, source_name: str) -> SystematicSource:
        try:
            return self._sources[source_name]
        except KeyError as exc:
            raise KeyError(f"unknown systematic source: {source_name}") from exc

    def run(
        self,
        source: SystematicSource,
        *,
        output_dir: Path,
        nominal_dir: Path,
        dry_run: bool = False,
        force: bool = False,
        max_workers: int = 1,
    ) -> list[VariationResult]:
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        if dry_run:
            return [
                self._dry_run_result(source, variation, output_dir=output_dir, nominal_dir=nominal_dir, force=force)
                for variation in source.variations
            ]

        runner = self._runners.get(source.name)
        if runner is None:
            raise NotImplementedError(f"no runner registered for source {source.name!r}")
        return [runner(source, variation) for variation in source.variations]

    def _dry_run_result(
        self,
        source: SystematicSource,
        variation: Variation,
        *,
        output_dir: Path,
        nominal_dir: Path,
        force: bool,
    ) -> VariationResult:
        run_hash = hash_config(
            {
                "source": source,
                "variation": variation,
                "nominal_dir": nominal_dir,
                "force": force,
            }
        )
        variation_dir = output_dir / "variations" / source.name / variation.name
        manifest_path = variation_dir / "manifest.json"
        return VariationResult(
            source=source.name,
            variation=variation.name,
            status="dry_run",
            target_value=float("nan"),
            target_uncertainty=float("nan"),
            artifacts={"variation_dir": variation_dir, "nominal_dir": nominal_dir, "run_hash": Path(run_hash)},
            manifest_path=manifest_path,
        )


def write_error_manifest(
    *,
    source: SystematicSource,
    variation: Variation,
    manifest_path: Path,
    error: Exception,
) -> Path:
    return write_manifest(
        manifest_path,
        {
            "status": "failed",
            "source": source.name,
            "variation": variation.name,
            "error_type": type(error).__name__,
            "error": str(error),
        },
    )
