# Robot Training Hub

A runnable React + TypeScript / FastAPI workshop platform for Booster K1 motion-tracking RL. SQLite owns the durable queue; outbound Python workers discover GPUs and execute frozen source snapshots using each host's existing Booster mjlab environment. No SSH access is given to participants.

## Current workshop deployment

Open **https://hub.example.edu/login**, or use the entry page **https://hub.example.edu/**. The backend runs on the Coordinator host, and all three real workers connect directly. The Mac can be offline.

Sign in as **admin@example.edu** with the password saved privately in `data/workshop/admin-credentials.txt`. Add participant emails and their limits in Admin → Participants, then generate/copy or email account passwords. Configure a sender in Admin → Settings → Email delivery. See [account and email setup](docs/EMAIL.md). An SMTP account is still needed for real delivery.

Environment choices are **1024 / 2048 / 4096**, default **2048**, with an **80% GPU memory ceiling**, **10 running jobs total**, and the stricter H100 memory reserve. Existing workstation sites are preserved. MPS remains off.

See [deployment status and operations](docs/CURRENT_STATUS.md), [real workshop guide](docs/REAL_WORKSHOP.md), and [validation](docs/VALIDATION.md). Private source: [Kyk0/robot-training-hub](https://github.com/Kyk0/robot-training-hub). The Mac data directory is an archive; the live database is on the workstation. The historical local/demo setup below remains available for isolated testing.

## Quick local demonstration

Requirements: Python 3.12+, uv, Git, Node 22+ and npm. The coordinator does not need CUDA.

```bash
cd /Users/operator/robot-training-hub
./scripts/bootstrap.sh           # install coordinator/web dependencies, fetch pinned source if absent
./scripts/demo.sh                # build, seed 18 attendees, launch coordinator + 3 mock workers
```

Open http://127.0.0.1:8000/login and click **Open admin demo** or **Open participant demo**. Local testing requires no email or registration; these shortcuts are disabled outside loopback development mode. The demo also prints a single-use administrator link. It uses `admin@workshop.example` and 18 approved `participant01@workshop.example` through `participant18@workshop.example` accounts. These are demo addresses. No password or long-lived login token is hardcoded.

If dependencies are already installed, run these in separate terminals:

```bash
export HUB_DEVELOPMENT=1
uv run robot-hub demo
uv run uvicorn hub.app:app --host 127.0.0.1 --port 8000 --no-access-log
# second terminal, same directory:
HUB_DEVELOPMENT=1 uv run robot-hub demo-workers
# third terminal: submit more work than the simulated GPU capacity
HUB_DEVELOPMENT=1 uv run python scripts/load_demo.py --iterations 200
```

Generate a fresh link whenever needed:

```bash
HUB_DEVELOPMENT=1 uv run robot-hub login-link admin@workshop.example
HUB_DEVELOPMENT=1 uv run robot-hub login-link participant01@workshop.example
```

Development email messages are written to private `data/mail/*.json`. Production requires SMTP. Demo workers, synthetic rewards, and JSON checkpoints are explicitly labeled in the UI. They do **not** produce a robot policy. Stop the demo with Ctrl-C. If a worker is interrupted while it owns a run, follow reconciliation below; do not just clear its journal.

## Included functionality

- Generated admin passwords stored as salted scrypt hashes; single-use, expiring magic links; approved-email allowlist; participant/admin authorization; opaque hashed sessions; secure HttpOnly cookies with HTTPS; origin and custom-header CSRF checks; login throttling. Admins can generate participant invitations without SMTP.
- Participant dashboard, training submission, run list, live progress/reward curves/logs, stop requests, results, source ZIP downloads, and a training repository link. Real CSV upload, approval, browser playback with the actual K1 meshes, and pinned Booster motion conversion. Per-run authenticated TensorBoard with streamed event files.
- `/admin`, `/admin/runs`, `/admin/servers`, `/admin/users`, `/admin/settings`: searchable runs, all-user inspection, priority, retry confirmed failures, cancellation, queue pause, attendee approval, per-user environment maximums, server/per-GPU limits, reserves, MPS settings, and audit history.
- Transactional partial unique SQLite index allows at most one QUEUED/STARTING/RUNNING job per user, including concurrent requests. A cancellation request retains the slot until a running process has actually exited.
- Durable best-fit GPU admission with configurable memory model, measured external memory, outstanding reservations, per-GPU concurrency, fairness through waiting-time priority, heartbeats, and worker quarantine.
- Workers claim each lease atomically once, retain a local journal, launch argv without a shell, isolate run directories, stream reports with idempotent log chunks, collect TensorBoard metrics, and upload SHA256-indexed artifacts. The latest three real `.pt` checkpoints and resolved YAML/JSON metadata are published at the end of a run. No arbitrary Python editing or remote command API is exposed.
- Frozen Booster and mjlab source from Git objects, fixed revision IDs, configuration, launcher, lockfiles, full-file hash manifest, integrity verification before and after execution, ZIP export, exact argv and module paths, dependency versions, and motion version/checksum records. Baselines with tracked uncommitted changes are refused.
- Existing legacy MPS and MPS v3 namespaces can be detected and attached to. Optional client thread and pinned-memory limits; safe fallback or required-MPS admission; no automatic daemon changes. A paired benchmark script records wall throughput, iteration metrics and GPU memory.

## Verified training integration

Repository: https://github.com/IntelligentRoboticsLab/booster_mjlab

Booster revision `d92e11395d961096d639446c0a8a176f12bb51da`; mjlab revision `b517e0c489139e7fcee95702cfb2b01931264985`. [Host observations](docs/HOSTS.md) include existing environments and hardware. The installed CLI was inspected on all three machines. Its tracking command is:

```bash
uv run train Mjlab-Tracking-Flat-Booster-K1 \
  --registry-name your-org/motions/walk:v0 \
  --env.scene.num-envs 512 \
  --agent.max-iterations 200 \
  --agent.logger tensorboard
```

This project's launcher uses the actual `TrainConfig.from_task`, `env.scene.num_envs`, `agent.max_iterations`, `agent.algorithm.learning_rate`, and `env.rewards[name].weight` configuration mechanisms. It invokes Booster's serialization patch and mjlab's existing `launch_training`. It does not implement PPO or invent reward CLI flags. The task's existing MuonPPO runner remains in use. Seed 42 is explicit; approved numeric overrides are applied before training. Exact resolved `env.yaml` and `agent.yaml` are saved by mjlab, and uploaded as artifacts. A W&B API key may be needed to retrieve approved motion artifacts, even with TensorBoard logging.

CSV motions are managed on the Motions page; the launcher checks their SHA256, converts using Booster's resampling/forward-kinematics utilities, and validates with the actual mjlab tracking MotionLoader. No W&B account is needed for CSV training. The optional API-managed W&B catalog requires immutable `:vN` versions, never `:latest`, and records artifact identity, digest, and actual checksum. Supply a SHA256 for `motion.npz` when known.

The frozen source imports override the installed Booster/mjlab packages; other dependencies come from the existing host virtual environment. All package versions and actual module locations are recorded. Keep that training environment stable during the workshop. Source checksums provide tamper detection; read-only POSIX files are an accidental-write barrier, not a security boundary against the service account or root. No participant code runs, and future custom reward Python requires a separate sandbox.

## Real coordinator deployment

Use a dedicated nonprivileged `robot-workshop` service account, not a personal account shared with students. Host owners must provision access to approved training environments, GPU devices, and storage.

1. Copy the project to `/srv/robot-training-hub`; run `scripts/bootstrap.sh`. Training dependencies are not installed on the coordinator.
2. Copy `deploy/coordinator.env.example` to `/etc/robot-hub/coordinator.env` (mode 0600), set a real HTTPS URL, SMTP host, sender, username, and password. `HUB_DEVELOPMENT=0` is the production default. SMTP uses STARTTLS.
3. Initialize the real administrator locally, without a preset password:

```bash
set -a
source /etc/robot-hub/coordinator.env
set +a
/srv/robot-training-hub/.venv/bin/robot-hub admin organizer@university.edu
```

4. Install `deploy/robot-hub.service` and enable it. Configure Caddy using `deploy/Caddyfile` with a real domain and DNS. Keep uvicorn on loopback; terminate HTTPS in Caddy. The service runs **one** coordinator process.
5. Log in by email. Approve participants; set allowed environment presets, motion catalog, resource profile, and host policy before enabling real workers.

```bash
sudo install -m 644 deploy/robot-hub.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now robot-hub
sudo systemctl status robot-hub
```

If SMTP is not ready, an operator with access to the coordinator data directory can generate a one-time login with `robot-hub login-link organizer@university.edu`. Treat that link as a credential. Do not publish it or keep it in tickets.

## Install each worker using its existing mjlab setup

The platform is copied into `~/robot-training-hub` on all three hosts. Install agent dependencies in its separate `.venv`; the training `.venv` is not modified:

```bash
# Worker A and Worker B
cd ~/robot-training-hub
./scripts/install-worker.sh /data/operator/booster_mjlab/.venv/bin/python
# Coordinator host: operator@192.0.2.20
cd ~/robot-training-hub
./scripts/install-worker.sh /home/operator/booster-mjlab/.venv/bin/python
```

In `/admin/servers`, add the host. Save the one-time enrollment token to `data/worker.token` with mode 0600. Set `HUB_COORDINATOR=https://hub.example.edu` in `data/worker.env`. Do not put tokens into shell history, source files, or systemd command lines. Enable institutional permission only after host-owner authorization; initial server enrollment does not authorize GPU work.

```bash
set -a
source data/worker.env
set +a
.venv/bin/robot-worker
```

For an approved dedicated account under `/srv`, install `deploy/robot-worker.service`. For the existing host account, `deploy/robot-worker-user.service` can be installed under `~/.config/systemd/user/` and started with `systemctl --user enable --now robot-worker-user`. It expects `~/robot-training-hub`. User service persistence after logout depends on site policy/linger. Students receive no SSH credentials.

A host managed by Slurm must run the worker **inside an allocated GPU job**; use `deploy/worker.slurm`, configure the institution's partition/account/reservation, and set server mode to `slurm`. The agent detects `srun`/Slurm configuration and reports `SLURM_JOB_ID`. The scheduler refuses direct admission to managed hosts. The sample does not submit jobs outside institutional allocation or promise automatic Slurm allocation renewal; allocate enough time for the workshop and handle expiry with reconciliation.

## Memory limits and scheduling

The configurable estimate is `(base_mb + num_envs * per_env_mb) * safety_factor`, rounded up. Defaults are deliberately provisional, not benchmark measurements. Each GPU's total memory minus observed external usage, outstanding job reservations, external reserve and safety margin determines admission. Best-fit preserves larger capacity; priority increases with waiting time. Per-user maximums and presets are checked when submitting. Per-server/per-GPU controls are frozen when a job is admitted, so later edits affect future placements.

Use 46,080 MiB reserve on shared Worker A/Worker B when researchers need 45 GiB free. Set concurrency conservatively until measured. Workers recheck free capacity just before launching and continuously request graceful stop of their own jobs if the reserve is crossed. Third-party allocations can race this check; an ordinary CUDA process is not a hardware-enforced partition. Enforce hard shared-memory quotas through institutional allocations, MIG when available and authorized, or validated MPS limits. The platform never kills unrelated processes. Legacy MPS may attribute memory to its daemon; conservative reservations remain in place, and the per-process usage display may be zero.

## MPS setup and benchmarking

See [MPS operations](docs/MPS.md). Existing services are attached to, never stopped. Configure `mps_pipe`, `mps_log`, interface generation, active-thread percentage, pinned-memory limit, and optional required-MPS mode in the admin UI. MPS v3 uses an existing named server and namespace and its discovered client pipe. Namespace limits can override client settings, so verify effective policy with the host owner.

```bash
uv run python scripts/benchmark.py \
  --source /path/to/a/frozen/run/source \
  --training-python /path/to/existing/booster/.venv/bin/python \
  --gpu GPU-full-uuid --concurrency 2 \
  --mps-config /path/to/reviewed-server-config.json \
  --output /path/to/new/benchmark-results --authorized
```

The benchmark uses the snapshot's exact task/motion/environments/iterations, first normal then MPS. Run repeatedly with alternating order for conclusions; warmup, concurrent external workloads and caches affect results. Do not assume MPS accelerates individual jobs. Benchmark runs consume real resources and must stay inside authorized allocations. No GPU benchmark was fabricated.

## Recovery, cancellation and maintenance

- Coordinator restart: leases, reservations, queue and sessions remain in SQLite. Workers continue local processes and retry reports; jobs are never automatically retried because of missing heartbeats.
- Worker restart or missing acknowledged process: server is quarantined, active runs retain capacity. Inspect its run journals and actual processes. Gracefully stop only workshop-owned clients; for stuck MPS clients follow NVIDIA client-specific termination instructions. In the admin server modal, affirm all old processes are stopped, then reconcile. Affected jobs become FAILED and may be explicitly retried.
- The worker has no automatic orphan reattachment. This is a deliberate safe limit. Systemd stops workers with SIGINT, and avoids forced SIGKILL of MPS clients.
- Queued cancellation is immediate. Running cancellation remains outstanding until the worker confirms exit. Cancellation during source preparation can take time before it reaches the launch guard; no shell commands are constructed from participant values.
- Logs are polled every 3 seconds; the UI shows the latest 128 KiB. Full logs are downloadable. TensorBoard rewards and the last 1,000 metric samples are shown. Artifacts are published after training exits; uploads retry on connectivity errors. Individual uploads are capped at 512 MiB and per-run publication at 2 GiB.
- `data/` contains the SQLite database, private email outbox, immutable source trees and artifacts; restrict permissions and back it up. `scripts/backup.py` performs online SQLite backup. Back up the matching snapshot/artifact directories as well. Apply a retention policy after the workshop; no automatic deletion is performed.
- Failed preparation or losing concurrent submissions can leave unreferenced source directories. Remove only verified unreferenced directories during planned offline maintenance. Frozen source consumes disk; plan for approximately 74 MiB per run plus output/checkpoints before compression.
- For source changes, rebuild the frontend and restart the coordinator. Stop accepting new jobs while updating worker code; finish/reconcile current jobs before agent restarts. Never edit a published run snapshot.

## Validation

```bash
uv sync --frozen --extra worker --extra test
uv run pytest -q
npm run build --prefix frontend
```

Tests cover authentication/allowlisting/session expiry, roles, ownership, CSRF, one outstanding job under concurrency, environment overrides, reservations, best-fit and Slurm admission, disconnected workers, coordinator restart, one-time claims, cancellation, artifact immutability/path traversal, MPS fallback/requirements, source integrity and execution, and an 18-user over-capacity queue.

The tested local HTTP demonstration completed 42 mock runs from 18 participants, verified a source ZIP containing 419 hashed files, and downloaded logs/checkpoints successfully. Repeat it with `HUB_DEVELOPMENT=1 uv run python scripts/verify_demo.py` after loading the demo.

See [validation results](docs/VALIDATION.md) for what was actually executed, including remaining external setup. Real SMTP delivery, HTTPS/domain deployment, sustained GPU training, MPS throughput and enforced institutional allocations require workshop-specific configuration and validation.

To resync source and built web assets to all three configured workshop hosts, run `./scripts/copy-workers.sh`. Runtime data, tokens and existing training environments are excluded from the release.

Git history is initialized on `main`, with both training dependencies pinned as submodules. See [Git workflow](docs/GIT_WORKFLOW.md) for branches, commits, submodule updates and connecting a shared remote.
