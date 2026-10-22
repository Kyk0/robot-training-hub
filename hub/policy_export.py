"""Frozen-source runner adapter. Reuses mjlab's native ONNX export at save time."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import time


def validate_onnx(path):
    import onnx

    onnx.checker.check_model(onnx.load(path, load_external_data=False))


def retain_checkpoints(output, checkpoint):
    """Bound this run's native checkpoints after a successful upstream save."""
    output = Path(output).resolve()
    checkpoint = Path(checkpoint)
    if (
        checkpoint.is_symlink()
        or not checkpoint.is_file()
        or not checkpoint.resolve().is_relative_to(output)
        or not re.fullmatch(r"model_\d+\.pt", checkpoint.name)
    ):
        return
    checkpoints = sorted(
        (
            p
            for p in checkpoint.parent.glob("model_*.pt")
            if not p.is_symlink()
            and p.is_file()
            and re.fullmatch(r"model_\d+\.pt", p.name)
        ),
        key=lambda p: int(p.stem.removeprefix("model_")),
    )
    retained = {checkpoint, *[p for p in checkpoints if p != checkpoint][-2:]}
    for old in checkpoints:
        if old not in retained:
            old.unlink()


def versioned_runner(base, output, spec):
    output = Path(output)

    class WorkshopPolicyRunner(base):
        def save(self, path, infos=None):
            super().save(path, infos)
            retain_checkpoints(output, path)
            _, _, exported = self._get_export_paths(path)
            exported = Path(exported)
            if not exported.is_file():
                print(
                    "[WARN] No ONNX policy was produced; inspect upstream export warnings.",
                    flush=True,
                )
                return
            if exported.stat().st_mtime_ns < Path(path).stat().st_mtime_ns:
                print(
                    "[WARN] ONNX was not updated for this checkpoint; skipping stale export.",
                    flush=True,
                )
                return
            try:
                validate_onnx(exported)
            except Exception:
                print(
                    "[WARN] ONNX validation failed; checkpoint retained without a policy version.",
                    flush=True,
                )
                return
            index = int(re.search(r"model_(\d+)", Path(path).stem).group(1))
            raw = exported.read_bytes()
            checksum = hashlib.sha256(raw).hexdigest()
            folder = output / "policies"
            folder.mkdir(exist_ok=True)
            stem = f"iteration_{index:06d}-{checksum[:12]}"
            destination = folder / (stem + ".onnx")
            if not destination.exists():
                temporary = destination.with_suffix(".tmp")
                temporary.write_bytes(raw)
                temporary.replace(destination)
                metadata = {
                    "iteration_index": index,
                    "completed_iterations": min(index + 1, spec["iterations"]),
                    "sha256": checksum,
                    "checkpoint": Path(path).name,
                    "created": time.time(),
                    "run_id": spec["run_id"],
                    "task": spec["task"],
                    "policy_interval": spec.get("policy_interval", 50),
                    "motion": spec["motion"],
                    "format": "onnx",
                    "retention": 10,
                }
                destination.with_suffix(".json").write_text(
                    json.dumps(metadata, indent=2)
                )
            # Retain the latest ten versioned exports; source snapshots stay immutable.
            for old in sorted(folder.glob("iteration_*.onnx"))[:-10]:
                old.unlink()
                old.with_suffix(".json").unlink(missing_ok=True)

    return WorkshopPolicyRunner
