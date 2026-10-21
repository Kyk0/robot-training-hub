"""Build a portable source release; never include runtime data or credentials."""

import argparse
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = [
    "hub",
    "frontend/src",
    "frontend/dist",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/tsconfig.json",
    "frontend/vite.config.ts",
    "frontend/index.html",
    "pyproject.toml",
    "uv.lock",
    "scripts",
    "tests",
    "deploy",
    "docs",
    "README.md",
    ".gitignore",
    ".gitattributes",
    ".gitmodules",
]
p = argparse.ArgumentParser()
p.add_argument("--output", type=Path, default=ROOT / "data/platform-release.tar.gz")
a = p.parse_args()
files = []
for name in INCLUDE:
    path = ROOT / name
    files.extend(sorted(path.rglob("*")) if path.is_dir() else [path])
files = [
    f
    for f in files
    if f.is_file()
    and not f.is_symlink()
    and "__pycache__" not in f.parts
    and f.suffix != ".pyc"
]
manifest = {
    str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files
}
(ROOT / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
a.output.parent.mkdir(parents=True, exist_ok=True)
with tarfile.open(a.output, "w:gz", format=tarfile.USTAR_FORMAT) as archive:
    for file in files + [ROOT / "release-manifest.json"]:
        archive.add(file, arcname=str(file.relative_to(ROOT)), recursive=False)
print(
    f"{a.output}: {len(files)} files, SHA256 {hashlib.sha256(a.output.read_bytes()).hexdigest()}"
)
