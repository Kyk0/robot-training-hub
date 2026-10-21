"""Git-object snapshots: tracked executable trees only, no workspace secrets or caches."""

import fcntl
import shutil
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import zipfile
from .db import pack

DENIED = {
    ".git",
    ".venv",
    ".env",
    "__pycache__",
    "node_modules",
    "secrets",
    "credentials",
    ".ssh",
}
EXTENSIONS = {
    ".py",
    ".toml",
    ".lock",
    ".md",
    ".txt",
    ".xml",
    ".stl",
    ".obj",
    ".png",
    ".jpg",
    ".yaml",
    ".yml",
    ".json",
    ".urdf",
    ".dae",
    ".mtl",
    ".webp",
    ".h",
    ".cpp",
    ".cu",
    ".cuh",
    ".glb",
    ".npz",
}


def safe_path(root, name):
    p = PurePosixPath(name)
    if (
        p.is_absolute()
        or not p.parts
        or any(x in ("..", "") for x in p.parts)
        or "\\" in name
    ):
        raise ValueError("Invalid artifact path")
    target = (root / name).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Path escapes root")
    return target


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_snapshot(repo, prefix, output):
    commit = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    if subprocess.check_output(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
        text=True,
    ).strip():
        raise ValueError(
            f"Baseline repository has tracked changes: {repo}; commit reviewed changes first"
        )
    archive = subprocess.check_output(["git", "-C", str(repo), "archive", commit])
    with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
        for item in tf:
            p = PurePosixPath(item.name)
            if not item.isfile() or item.size > 32 * 1024 * 1024:
                continue
            if any(
                x in DENIED
                or x.startswith(".env")
                or "secret" in x.lower()
                or x.endswith(".pem")
                for x in p.parts
            ):
                continue
            if p.parts[0] not in (
                "src",
                "assets",
                "pyproject.toml",
                "uv.lock",
                "README.md",
                "LICENSE",
                "LICENSE.txt",
            ):
                continue
            if p.suffix.lower() not in EXTENSIONS and p.name != "LICENSE":
                continue
            target = output / prefix / item.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tf.extractfile(item).read())
    return commit


def freeze(root):
    for p in root.rglob("*"):
        if p.is_file():
            p.chmod(0o444)
    for p in sorted(root.rglob("*"), reverse=True):
        if p.is_dir():
            p.chmod(0o555)
    root.chmod(0o555)


def create_snapshot(cfg, key, spec):
    root = cfg.data / "snapshots" / key
    commits = {}
    for name, repo in [("booster_mjlab", cfg.base_repo), ("mjlab", cfg.mjlab_repo)]:
        commits[name] = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip()
        if subprocess.check_output(
            ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
            text=True,
        ).strip():
            raise ValueError(f"Baseline has tracked modifications: {repo}")
    bases = cfg.data / "bases"
    bases.mkdir(parents=True, exist_ok=True)
    cached = bases / sha(pack(commits).encode())
    with (bases / "prepare.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not cached.exists():
            temporary = bases / ("preparing-" + os.urandom(8).hex())
            temporary.mkdir()
            for name, repo in [
                ("booster_mjlab", cfg.base_repo),
                ("mjlab", cfg.mjlab_repo),
            ]:
                git_snapshot(repo, name, temporary)
            temporary.rename(cached)
            freeze(cached)
    root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(cached, root)
    root.chmod(0o755)
    (root / "hub_config.json").write_text(pack(spec))
    (root / "hub_launch.py").write_bytes(
        Path(__file__).with_name("training_entry.py").read_bytes()
    )
    (root / "mock_train.py").write_bytes(
        Path(__file__).with_name("mock_train.py").read_bytes()
    )
    (root / "hub_motion.py").write_bytes(
        Path(__file__).with_name("csv_motion.py").read_bytes()
    )
    hashes = {
        str(p.relative_to(root)): sha(p.read_bytes())
        for p in root.rglob("*")
        if p.is_file()
    }
    manifest = {
        "commits": commits,
        "files": hashes,
        "configuration": spec,
        "entrypoint": "hub_launch.py",
        "motion": spec.get("motion"),
        "schema": 1,
    }
    raw = pack(manifest).encode()
    (root / "manifest.json").write_bytes(raw)
    freeze(root)
    return sha(raw)


def verify(root, expected=None):
    raw = (root / "manifest.json").read_bytes()
    if expected and sha(raw) != expected:
        raise ValueError("Manifest checksum mismatch")
    manifest = json.loads(raw)
    actual = {
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and p != root / "manifest.json"
    }
    if actual != set(manifest["files"]):
        raise ValueError("Source file list changed")
    for name, checksum in manifest["files"].items():
        p = safe_path(root, name)
        if p.is_symlink() or sha(p.read_bytes()) != checksum:
            raise ValueError(f"Source changed: {name}")
    return manifest


def zip_tree(root):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob("*")):
            if p.is_file() and not p.is_symlink():
                z.write(p, str(p.relative_to(root)))
    return stream.getvalue()


def extract_snapshot(data, root, expected):
    root.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(x.file_size for x in z.infolist()) > 512 * 1024 * 1024:
            raise ValueError("Oversized source archive")
        for item in z.infolist():
            if item.is_dir():
                continue
            target = safe_path(root, item.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(item))
    result = verify(root, expected)
    freeze(root)
    return result
