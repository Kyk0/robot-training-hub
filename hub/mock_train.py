"""CPU demonstration only. Produces synthetic metrics and a clearly labeled checkpoint."""

import json
import math
import os
from pathlib import Path
import time

source = Path(__file__).resolve().parent
spec = json.loads((source / "hub_config.json").read_text())
output = Path(os.environ["HUB_RUN_OUTPUT"])
output.mkdir(parents=True, exist_ok=True)
(output / "resolved.json").write_text(
    json.dumps({"mode": "MOCK — not a robot policy", "configuration": spec}, indent=2)
)
for step in range(1, spec["iterations"] + 1):
    time.sleep(float(os.getenv("HUB_MOCK_STEP_SECONDS", "0.15")))
    reward = round(0.5 + 2.8 * (1 - math.exp(-step / 40)) + 0.05 * math.sin(step), 4)
    print(
        "HUB_METRIC "
        + json.dumps(
            {
                "iteration": step,
                "reward": reward,
                "iteration_seconds": 0.15,
                "fps": spec["num_envs"] * 24 / 0.15,
            }
        ),
        flush=True,
    )
    if step % 25 == 0 or step == spec["iterations"]:
        (output / f"mock_checkpoint_{step}.json").write_text(
            json.dumps({"mock": True, "iteration": step, "reward": reward})
        )
print("Mock run completed. This is not GPU training.", flush=True)
