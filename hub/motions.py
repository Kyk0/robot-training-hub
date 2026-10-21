"""Validated Booster K1 CSV storage and robot preview metadata."""

import csv
import hashlib
import io
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from .db import now, pack, uid, unpack

JOINT_NAMES = [
    "Head_Yaw",
    "Head_Pitch",
    "Left_Shoulder_Pitch",
    "Left_Shoulder_Roll",
    "Left_Elbow_Pitch",
    "Left_Elbow_Yaw",
    "Right_Shoulder_Pitch",
    "Right_Shoulder_Roll",
    "Right_Elbow_Pitch",
    "Right_Elbow_Yaw",
    "Left_Hip_Pitch",
    "Left_Hip_Roll",
    "Left_Hip_Yaw",
    "Left_Knee_Pitch",
    "Left_Ankle_Pitch",
    "Left_Ankle_Roll",
    "Right_Hip_Pitch",
    "Right_Hip_Roll",
    "Right_Hip_Yaw",
    "Right_Knee_Pitch",
    "Right_Ankle_Pitch",
    "Right_Ankle_Roll",
]
CSV_HEADER = [
    "root_pos_x",
    "root_pos_y",
    "root_pos_z",
    "root_quat_x",
    "root_quat_y",
    "root_quat_z",
    "root_quat_w",
    "aahead_yaw_joint",
    "aahead_pitch_joint",
    *[n.lower() + "_joint" for n in JOINT_NAMES[2:]],
]
MAX_BYTES = 20 * 1024 * 1024


def parse_csv(raw, fps):
    if not 1 <= fps <= 240 or not math.isfinite(fps):
        raise ValueError("Frame rate must be between 1 and 240 Hz")
    if len(raw) > MAX_BYTES:
        raise ValueError("CSV must be smaller than 20 MiB")
    try:
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    except (UnicodeError, csv.Error):
        raise ValueError("Upload a UTF-8 CSV file")
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("CSV is empty")
    header = None
    try:
        [float(v) for v in rows[0]]
    except ValueError:
        header = [v.strip() for v in rows.pop(0)]
        if header != CSV_HEADER and header != [
            "x",
            "y",
            "z",
            "qx",
            "qy",
            "qz",
            "qw",
            *JOINT_NAMES,
        ]:
            raise ValueError(
                "Expected Booster K1 root XYZ, quaternion XYZW, and 22 joints in the documented order"
            )
    if not 3 <= len(rows) <= 60000:
        raise ValueError("Motion must contain 3 to 60,000 frames")
    data = []
    for index, row in enumerate(rows, 1):
        if len(row) != 29:
            raise ValueError(f"Frame {index}: expected 29 columns, found {len(row)}")
        try:
            frame = [float(v) for v in row]
        except ValueError:
            raise ValueError(f"Frame {index} contains a non-numeric value")
        if not all(math.isfinite(v) and abs(v) < 10000 for v in frame):
            raise ValueError(f"Frame {index} contains invalid values")
        norm = math.sqrt(sum(v * v for v in frame[3:7]))
        if not 0.9 <= norm <= 1.1:
            raise ValueError(f"Frame {index}: root quaternion must have unit length")
        frame[3:7] = [v / norm for v in frame[3:7]]
        data.append(frame)
    return {
        "fps": fps,
        "frames": len(data),
        "duration": (len(data) - 1) / fps,
        "joint_names": JOINT_NAMES,
        "data": data,
        "format": "k1-xyz-xyzw-radians",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def store_motion(db, owner, raw, name, fps=50, shared=False):
    preview = parse_csv(raw, fps)
    key = uid()
    folder = db.cfg.data / "motions" / key
    folder.mkdir(parents=True, mode=0o700)
    (folder / "input.csv").write_bytes(raw)
    (folder / "preview.json").write_text(pack(preview))
    (folder / "input.csv").chmod(0o444)
    (folder / "preview.json").chmod(0o444)
    with db.tx() as c:
        c.execute(
            "INSERT INTO motions(id,user_id,label,filename,fps,frames,duration,sha256,approved,shared,created) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                key,
                owner["id"],
                name[:120],
                "input.csv",
                fps,
                preview["frames"],
                preview["duration"],
                preview["sha256"],
                owner["role"] == "admin",
                shared and owner["role"] == "admin",
                now(),
            ),
        )
        db.audit(
            c,
            owner["id"],
            "upload-motion",
            {"motion": key, "sha256": preview["sha256"]},
        )
        return public_motion(
            c.execute("SELECT * FROM motions WHERE id=?", (key,)).fetchone()
        )


def public_motion(row):
    d = dict(row)
    return {**d, "kind": "csv", "artifact": "upload:" + d["id"]}


def visible_motions(c, user, approved_only=False):
    return [
        public_motion(r)
        for r in c.execute(
            "SELECT * FROM motions WHERE (? OR user_id=? OR shared=1) AND (?=0 OR approved=1) ORDER BY created DESC",
            (user["role"] == "admin", user["id"], approved_only),
        )
    ]


def robot_model(cfg):
    root = cfg.base_repo / "src/booster_mjlab/robots/booster_k1/xmls"
    doc = ET.parse(root / "k1.xml").getroot()
    materials = {
        m.get("name"): [float(x) for x in m.get("rgba", "0.65 0.65 0.65 1").split()]
        for m in doc.findall("asset/material")
    }
    meshes = {
        m.get("name"): {
            "file": m.get("file"),
            "scale": [float(x) for x in m.get("scale", "1 1 1").split()],
        }
        for m in doc.findall("asset/mesh")
    }

    def vector(element, key, default):
        return [float(x) for x in element.get(key, default).split()]

    def body(element):
        j = element.find("joint")
        return {
            "name": element.get("name"),
            "pos": vector(element, "pos", "0 0 0"),
            "quat": vector(element, "quat", "1 0 0 0"),
            "joint": None
            if j is None or j.get("type") == "free"
            else {
                "name": j.get("name"),
                "axis": vector(j, "axis", "0 0 1"),
                "pos": vector(j, "pos", "0 0 0"),
            },
            "geoms": [
                {
                    "mesh": g.get("mesh"),
                    "pos": vector(g, "pos", "0 0 0"),
                    "quat": vector(g, "quat", "1 0 0 0"),
                    "color": materials.get(g.get("material"), [0.65, 0.65, 0.65, 1]),
                }
                for g in element.findall("geom")
                if g.get("mesh") and g.get("group") == "2"
            ],
            "children": [body(b) for b in element.findall("body")],
        }

    return {
        "meshes": meshes,
        "body": body(doc.find("worldbody/body")),
        "joint_names": JOINT_NAMES,
        "model": "Booster K1 · 22 DoF",
    }
