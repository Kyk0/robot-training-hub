# Policy versions and exports

Open **Policies** in the sidebar (`/policies`). Participants see their own exports; admins see every participant's policies. Each entry links to its training run and offers:

- **ONNX**: download the inference model alone for a compatible simulator or robot runtime.
- **PT checkpoint**: download the matching retained training checkpoint to resume mjlab training; older policy versions may no longer have a retained PT file.
- **Export policy**: download a ZIP containing `policy.onnx`, resolved YAML configuration and a provenance manifest with policy/source hashes, run ID, approved motion and training configuration.

New runs default to an export/checkpoint interval of **50 learning iterations**. The New training form also offers 100 or 200. This sets the pinned mjlab runner's real `agent.save_interval`; it is not a simulator timestep interval. mjlab also saves initially and finally. Checkpoint indices in the policy list are zero-based (for example model_50.pt is saved after the 51st iteration).

The frozen launcher subclasses the registered task runner only to preserve and validate the ONNX file already exported by mjlab. It does not replace the RL algorithm. Every version includes an iteration index and content hash. The **latest ten versions per run** are retained locally and on the coordinator to bound disk usage. Older versions can disappear from the list; source snapshots stay immutable. PT checkpoints retain the existing latest-three publication policy.

The outbound `robot-training-hub-policy-sync` user service checks source manifests and ONNX structure, then publishes new versions about every 15 seconds. It uses that host's existing worker credential, journal lease, and training Python. It neither starts training nor changes MPS. It can be installed alongside active GPU workers without restarting or stopping them:

```bash
cd /Users/operator/robot-training-hub
.venv/bin/python scripts/install_policy_publishers.py
```

It also publishes existing valid ONNX files from older runs, including running jobs, using their original checkpoint interval. Already-running jobs keep their frozen source and save settings. Publication appends immutable versioned policy files; ordinary finalized checkpoints/configuration cannot be overwritten. Invalid, stale or incomplete ONNX files are skipped and reported in publisher/training logs.

Worker A/Worker B user services use runtime links when LDAP and login home paths differ. Reinstall those links after reboot until persistent service management is arranged with the host administrator. GPU worker installation and SMTP setup remain separate.

An exported ONNX is an inference artifact with tracking/motion metadata. Export verification does not establish trained policy quality or successful robot-hardware deployment. The browser motion player still previews reference CSV motion rather than running the learned policy.
