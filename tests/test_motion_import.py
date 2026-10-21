import csv
import hashlib
import io
import json
import math

import pytest

from hub.motions import JOINT_NAMES, MUJOCO_COLUMNS, parse_csv


def cartwheel_csv(change=None):
    # Different values for every joint expose incorrect positional mappings.
    columns = [
        "time_s",
        "root_x_m",
        "root_y_m",
        "root_z_m",
        "root_qw",
        "root_qx",
        "root_qy",
        "root_qz",
        *reversed(MUJOCO_COLUMNS[7:]),
        *[c + "_s" for c in MUJOCO_COLUMNS[7:]],
    ]
    rows = []
    for i in range(4):
        row = {c: 0 for c in columns}
        row.update(time_s=i / 50, root_z_m=0.6, root_qw=0.8, root_qx=0.6)
        row.update({c: (j + 1) / 100 for j, c in enumerate(MUJOCO_COLUMNS[7:])})
        rows.append(row)
    if change:
        change(columns, rows)
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(columns)
    writer.writerows([[r[c] for c in columns] for r in rows])
    return text.getvalue().encode()


def test_named_cartwheel_maps_quaternion_and_every_joint():
    motion = parse_csv(cartwheel_csv(), 50)
    assert motion["source_format"] == "mujoco-named-radians"
    assert motion["frames"] == 4
    assert motion["data"][0][:7] == pytest.approx([0, 0, 0.6, 0.6, 0, 0, 0.8])
    assert motion["data"][0][7:] == pytest.approx([(j + 1) / 100 for j in range(22)])
    assert motion["joint_names"] == JOINT_NAMES


@pytest.mark.parametrize("problem", ["missing", "duplicate", "unknown", "nan", "time"])
def test_named_cartwheel_rejects_ambiguous_or_invalid_data(problem):
    def change(columns, rows):
        if problem == "missing":
            columns.remove(MUJOCO_COLUMNS[-1])
        elif problem == "duplicate":
            columns.append("root_qw")
        elif problem == "unknown":
            columns.append("unrecognized_joint")
            for row in rows:
                row["unrecognized_joint"] = 0
        elif problem == "nan":
            rows[1][MUJOCO_COLUMNS[-1] + "_s"] = math.nan
        else:
            rows[1]["time_s"] = 0.04

    with pytest.raises(ValueError):
        parse_csv(cartwheel_csv(change), 50)


def test_cartwheel_upload_preserves_original_and_freezes_training_checksum(setup, job):
    _, _, cfg, client = setup
    admin = client("admin@example.org")
    raw = cartwheel_csv()
    response = admin.post("/api/motions?label=Cartwheel&fps=50", content=raw)
    assert response.status_code == 201, response.text
    motion = response.json()
    folder = cfg.data / "motions" / motion["id"]
    assert (folder / "original.csv").read_bytes() == raw
    assert (folder / "original.csv").stat().st_mode & 0o222 == 0
    canonical = (folder / "input.csv").read_bytes()
    assert canonical != raw
    assert all(len(row) == 29 for row in csv.reader(io.StringIO(canonical.decode())))
    assert hashlib.sha256(canonical).hexdigest() == motion["sha256"]
    preview = admin.get(f"/api/motions/{motion['id']}/preview").json()
    assert preview["original_sha256"] == hashlib.sha256(raw).hexdigest()
    assert preview["sha256"] == motion["sha256"]
    assert parse_csv(canonical, 50)["data"] == preview["data"]
    assert admin.get(f"/api/motions/{motion['id']}/download").content == canonical
    run = admin.post("/api/runs", json={**job, "motion_id": motion["id"]})
    assert run.status_code == 201, run.text
    frozen = json.loads(
        (cfg.data / "snapshots" / run.json()["id"] / "hub_config.json").read_text()
    )
    assert frozen["motion"]["sha256"] == hashlib.sha256(canonical).hexdigest()
