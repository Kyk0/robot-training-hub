"""CSV-to-tracking adapter using the pinned Booster motion and mjlab FK utilities."""

import hashlib
import json
from pathlib import Path

JOINTS = [
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


def convert_csv(path, output, fps, expected):
    import numpy as np
    import torch
    from booster_mjlab.motion import MotionFile
    from booster_mjlab.scripts.upload_motion import (
        _resample_motion,
        _build_scene_and_sim,
        _run_forward_kinematics,
        _validate_output,
        _default_output_fps,
    )

    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    if checksum != expected:
        raise ValueError("CSV checksum does not match the approved motion")
    first = path.read_text(encoding="utf-8-sig").splitlines()[0]
    try:
        [float(v) for v in first.split(",")]
        skip = 0
    except ValueError:
        skip = 1
    values = np.atleast_2d(
        np.loadtxt(path, delimiter=",", skiprows=skip, dtype=np.float32)
    )
    if values.shape[1] != 29 or len(values) < 3 or not np.isfinite(values).all():
        raise ValueError("Invalid Booster K1 CSV")
    rotations = values[:, 3:7]
    rotations = rotations / np.linalg.norm(rotations, axis=1, keepdims=True)
    motion = MotionFile(
        fps=fps, root_pos=values[:, :3], root_rot=rotations, dof_pos=values[:, 7:]
    )
    target_fps = _default_output_fps()
    resampled = _resample_motion(motion, target_fps, torch.device("cpu"))
    scene, sim, robot = _build_scene_and_sim(device="cpu")
    indexes = robot.find_joints(JOINTS, preserve_order=True)[0]
    aligned_pos = torch.zeros_like(resampled.joint_pos)
    aligned_vel = torch.zeros_like(resampled.joint_vel)
    aligned_pos[:, indexes] = resampled.joint_pos
    aligned_vel[:, indexes] = resampled.joint_vel
    resampled.joint_pos = aligned_pos
    resampled.joint_vel = aligned_vel
    data = _run_forward_kinematics(resampled, scene, sim, robot)
    np.savez(output, **data)
    _validate_output(output, robot, device="cpu")
    manifest = {
        "kind": "csv",
        "csv_sha256": checksum,
        "input_fps": fps,
        "output_fps": target_fps,
        "input_frames": len(values),
        "output_frames": resampled.num_frames,
        "npz_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "joint_order": JOINTS,
        "converter": "booster_mjlab.scripts.upload_motion forward kinematics",
    }
    output.with_name("manifest.json").write_text(json.dumps(manifest, indent=2))
    print("CSV motion converted and validated:", json.dumps(manifest), flush=True)
    return output
