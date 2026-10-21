"""Outbound-only ONNX publisher; safe alongside an already-running GPU worker."""

import argparse
import hashlib
import json
import logging
from pathlib import Path
import re
import subprocess
import time
import httpx
from .snapshots import verify

log = logging.getLogger("policy-sync")


def sync_once(client, root, training_python, state, checked):
    published = 0
    for journal in sorted(root.glob("*/journal.json")):
        try:
            directory = journal.parent
            if not re.fullmatch(r"[a-f0-9]{32}", directory.name):
                continue
            record = json.loads(journal.read_text())
            if not record.get("lease"):
                continue
            output = directory / "output"
            sources = sorted((output / "policies").glob("iteration_*.onnx"))
            native = not sources
            if native:
                sources = sorted(
                    output.glob("training/**/*.onnx"), key=lambda p: p.stat().st_mtime
                )[-1:]
            for source in sources:
                if source.is_symlink():
                    continue
                stat = source.stat()
                stamp = f"{stat.st_mtime_ns}:{stat.st_size}"
                state_key = str(source.relative_to(root))
                if state.get(state_key) == stamp or time.time() - stat.st_mtime < 3:
                    continue
                headers = {"X-Job-Lease": record["lease"]}
                context = client.get(
                    f"/api/worker/runs/{directory.name}/policy-context", headers=headers
                )
                if context.status_code == 409:
                    continue
                context.raise_for_status()
                context = context.json()
                if directory.name not in checked:
                    verify(directory / "source", context["snapshot"])
                    checked.add(directory.name)
                if native:
                    checkpoints = sorted(
                        output.glob("training/**/*.pt"), key=lambda p: p.stat().st_mtime
                    )
                    if (
                        not checkpoints
                        or stat.st_mtime < checkpoints[-1].stat().st_mtime
                    ):
                        continue
                    index = int(
                        re.search(r"model_(\d+)", checkpoints[-1].stem).group(1)
                    )
                else:
                    index = int(re.search(r"iteration_(\d+)", source.stem).group(1))
                raw = source.read_bytes()
                if source.stat().st_mtime_ns != stat.st_mtime_ns:
                    continue
                checksum = hashlib.sha256(raw).hexdigest()
                cache = directory / "policy-publish"
                cache.mkdir(exist_ok=True)
                candidate = cache / (checksum + ".onnx")
                candidate.write_bytes(raw)
                subprocess.run(
                    [
                        training_python,
                        "-c",
                        "import onnx,sys;onnx.checker.check_model(onnx.load(sys.argv[1],load_external_data=False))",
                        str(candidate),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                policy_path = f"policies/iteration_{index:06d}-{checksum[:12]}.onnx"
                metadata = {
                    "iteration_index": index,
                    "completed_iterations": min(
                        index + 1, context["spec"]["iterations"]
                    ),
                    "sha256": checksum,
                    "source_snapshot": context["snapshot"],
                    "run_id": directory.name,
                    "created": stat.st_mtime,
                    "format": "onnx",
                    "policy_interval": context["spec"].get("policy_interval", 100),
                }
                metadata_raw = (
                    json.dumps(metadata).encode()
                    if native
                    else source.with_suffix(".json").read_bytes()
                )
                if json.loads(metadata_raw)["sha256"] != checksum:
                    raise ValueError("Policy metadata checksum mismatch")
                expired = False
                for path, content in (
                    (policy_path, raw),
                    (policy_path[:-5] + ".json", metadata_raw),
                ):
                    response = client.put(
                        f"/api/worker/runs/{directory.name}/artifact",
                        params={"path": path},
                        headers={**headers, "Content-Type": "application/octet-stream"},
                        content=content,
                    )
                    if (
                        response.status_code == 409
                        and "retention window" in response.text
                    ):
                        expired = True
                        break
                    response.raise_for_status()
                state[state_key] = stamp
                candidate.unlink(missing_ok=True)
                if not expired:
                    published += 1
                    log.info(
                        "Published checked ONNX for %s at checkpoint index %s",
                        directory.name,
                        index,
                    )
        except Exception as exc:
            log.warning(
                "Policy publication deferred for %s: %s",
                journal.parent.name,
                type(exc).__name__,
            )
    return published


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--coordinator", required=True)
    p.add_argument("--token-file", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--training-python", required=True)
    p.add_argument("--once", action="store_true")
    args = p.parse_args()
    if not args.coordinator.startswith(
        ("https://", "http://127.0.0.1:", "http://localhost:")
    ):
        p.error("HTTPS is required outside loopback")
    logging.basicConfig(level=logging.INFO)
    root = args.root.resolve()
    path = root.parent / "policy-sync-state.json"
    state = json.loads(path.read_text()) if path.exists() else {}
    checked = set()
    with httpx.Client(
        base_url=args.coordinator,
        headers={"Authorization": "Bearer " + args.token_file.read_text().strip()},
        timeout=60,
        transport=httpx.HTTPTransport(retries=3),
    ) as client:
        while True:
            try:
                sync_once(client, root, args.training_python, state, checked)
            except Exception as exc:
                log.warning("Publication deferred: %s", type(exc).__name__)
                if args.once:
                    raise
            finally:
                temporary = path.with_suffix(".tmp")
                temporary.write_text(json.dumps(state))
                temporary.chmod(0o600)
                temporary.replace(path)
            if args.once:
                break
            time.sleep(15)


if __name__ == "__main__":
    main()
