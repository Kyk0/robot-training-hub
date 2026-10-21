"""Policy catalog helpers and bounded version retention."""

import re
from pathlib import Path

VERSION = re.compile(r"^policies/(iteration_(\d+)-[a-f0-9]{12})\.(onnx|json)$")


def obsolete_versions(rows, incoming, keep=10):
    match = VERSION.fullmatch(incoming)
    if not match:
        return []
    groups = {
        VERSION.fullmatch(row["path"]).group(1)
        for row in rows
        if VERSION.fullmatch(row["path"])
    }
    groups.add(match.group(1))
    retained = set(sorted(groups)[-keep:])
    if match.group(1) not in retained:
        raise ValueError("Policy version is outside the retention window")
    return [
        row["path"]
        for row in rows
        if (m := VERSION.fullmatch(row["path"])) and m.group(1) not in retained
    ]
