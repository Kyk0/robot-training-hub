"""Executed FROM the frozen snapshot, with each host's preinstalled training interpreter.
Only reviewed numeric configuration is accepted; no participant Python is evaluated.
"""

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve().parent
OUTPUT = Path(os.environ["HUB_RUN_OUTPUT"]).resolve()
sys.path[:0] = [str(SOURCE / "booster_mjlab/src"), str(SOURCE / "mjlab/src")]


def main():
    import booster_mjlab.scripts.train as train
    import mjlab.scripts.train as mjtrain
    import mjlab.tasks
    from dataclasses import replace

    for module in (train, mjtrain):
        if not Path(module.__file__).resolve().is_relative_to(SOURCE):
            raise RuntimeError("Training imported code outside frozen snapshot")
    spec = json.loads((SOURCE / "hub_config.json").read_text())
    cfg = train.TrainConfig.from_task(spec["task"])
    cfg.env.scene.num_envs = spec["num_envs"]
    cfg.env.seed = spec["seed"]
    cfg.agent.seed = spec["seed"]
    cfg.agent.max_iterations = spec["iterations"]
    cfg.agent.experiment_name = "workshop"
    cfg.agent.run_name = spec["run_id"]
    cfg.agent.logger = "tensorboard"
    cfg.agent.save_interval = min(100, spec["iterations"])
    if spec.get("learning_rate") is not None:
        cfg.agent.algorithm.learning_rate = spec["learning_rate"]
    for key, value in spec.get("rewards", {}).items():
        cfg.env.rewards[key].weight = value
    OUTPUT.mkdir(parents=True, exist_ok=True)
    versions = {
        d.metadata["Name"]: d.version
        for d in importlib.metadata.distributions()
        if d.metadata["Name"]
    }
    (OUTPUT / "environment.json").write_text(
        json.dumps(
            {
                "python": sys.version,
                "executable": sys.executable,
                "packages": versions,
                "module_paths": {"booster": train.__file__, "mjlab": mjtrain.__file__},
            },
            indent=2,
        )
    )
    if "--validate-only" in sys.argv:
        (OUTPUT / "validation.json").write_text(
            json.dumps(
                {
                    "task": spec["task"],
                    "num_envs": cfg.env.scene.num_envs,
                    "iterations": cfg.agent.max_iterations,
                    "logger": cfg.agent.logger,
                    "rewards": {k: v.weight for k, v in cfg.env.rewards.items()},
                    "module_paths": {
                        "booster": train.__file__,
                        "mjlab": mjtrain.__file__,
                    },
                },
                indent=2,
            )
        )
        print(
            "Frozen source imports and task configuration validated; no GPU training launched.",
            flush=True,
        )
        return
    if spec["motion"]["artifact"].startswith("upload:"):
        from hub_motion import convert_csv

        motion_file = convert_csv(
            OUTPUT / "motion/input.csv",
            OUTPUT / "motion/motion.npz",
            spec["motion"]["fps"],
            spec["motion"]["sha256"],
        )
    else:
        import wandb

        artifact = wandb.Api().artifact(spec["motion"]["artifact"])
        motion_dir = artifact.download(root=str(OUTPUT / "motion"))
        motion_file = Path(motion_dir) / "motion.npz"
        checksum = hashlib.sha256(motion_file.read_bytes()).hexdigest()
        expected = spec["motion"].get("sha256")
        if expected and expected != checksum:
            raise ValueError("Approved motion checksum mismatch")
        (OUTPUT / "motion.json").write_text(
            json.dumps(
                {
                    "requested": spec["motion"]["artifact"],
                    "resolved": artifact.qualified_name,
                    "digest": artifact.digest,
                    "sha256": checksum,
                },
                indent=2,
            )
        )
    cfg.env.commands["motion"].motion_file = str(motion_file)
    if "--prepare-only" in sys.argv:
        print("Motion prepared and validated; no GPU training launched.", flush=True)
        return
    cfg = replace(
        cfg, registry_name=None, log_root=str(OUTPUT / "training"), gpu_ids=[0]
    )
    train._patch_dump_yaml()
    mjtrain.launch_training(task_id=spec["task"], args=cfg)


if __name__ == "__main__":
    main()
