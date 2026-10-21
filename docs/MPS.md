# CUDA MPS operations

The worker performs read-only capability/status checks and attaches clients to an existing, approved service. It never changes GPU compute mode, starts a daemon implicitly, sends `quit`, deletes namespaces, or kills pre-existing clients. NVIDIA's [MPS documentation](https://docs.nvidia.com/deploy/mps/latest/index.html), [environment variables](https://docs.nvidia.com/deploy/mps/appendix-environment-variables.html), and [v3 interface](https://docs.nvidia.com/deploy/mps/mpsv3-interface.html) are the operational references.

## Before enabling

Have the host owner confirm permission, driver/CUDA generation, GPU compatibility, account/UID policy, memory reservations, and institutional allocation. `nvidia-cuda-mps-control` existing on PATH alone does not establish a usable service. MPS clients and sockets must be accessible to the same intended UID; never use personal-account sharing as a workaround. Worker A/Worker B must retain the configured 45 GiB external reserve when applicable.

For a dedicated service account, a site administrator may explicitly provision a new private legacy daemon using the separate script below. This action is **not** performed by the application:

```bash
# Only after the host owner authorizes a new dedicated service.
# Choose a fresh private pipe, not the location of an existing shared daemon.
install -d -m 700 /srv/robot-training-hub/data/mps-pipe /srv/robot-training-hub/data/mps-log
export CUDA_MPS_PIPE_DIRECTORY=/srv/robot-training-hub/data/mps-pipe
export CUDA_MPS_LOG_DIRECTORY=/srv/robot-training-hub/data/mps-log
nvidia-cuda-mps-control -d
printf 'get_server_list\n' | nvidia-cuda-mps-control
```

Run this as the authorized workshop service user; do not change compute modes or stop another user's daemon. Configure these exact directories in the admin server modal. The daemon may start its GPU server only when the first client attaches. Set a conservative pinned-device memory limit and active-thread percentage, and choose `MPS required` when fallback would invalidate an experiment. Disabling MPS in the UI affects future clients, not existing ones or the daemon.

## Legacy vs v3

Legacy v2 uses interactive stdin queries such as `get_server_list`. The worker only uses this query for a host configured as `legacy`. MPS v3 uses typed CLI modules and an existing named server/namespace. Set the root pipe directory, MPS kind `v3`, named server and namespace in the UI; the worker queries `namespace list NAME --server=SERVER --format=csv,noheader` and uses its returned client pipe. It does not create or modify the namespace.

Client `CUDA_MPS_ACTIVE_THREAD_PERCENTAGE` and `CUDA_MPS_PINNED_DEVICE_MEM_LIMIT` are recorded in execution metadata. Under v3, namespace limits interact differently with client variables and can override thread percentages; the host owner must inspect effective limits. Do not equate a percentage with an exclusive GPU partition. No v3 service or GPU performance claim has been validated by this project yet.

## Containers

The supported deployment uses systemd on the host, avoiding socket/UID ambiguity. For containers, validate NVIDIA Container Toolkit/driver compatibility and mount the configured MPS pipe and log directories at matching paths, preserve compatible UID ownership and GPU UUID visibility, and confirm an actual client attaches. Do not expose MPS control sockets broadly or grant privileged containers. Container compatibility is not asserted without a site-specific test.

## Cancellation and recovery

The worker sends SIGINT to its own process group for graceful CUDA synchronization. Non-MPS jobs may receive TERM and KILL if they fail to stop. A stuck MPS client is retained and the server quarantined instead of forcibly killed. An authorized operator must inspect the client's actual PID and MPS server, use the correct client-specific termination procedure for that generation, then confirm the process exited before reconciliation. Never terminate the shared daemon or unrelated clients.

## Throughput experiment

`scripts/benchmark.py` compares equal concurrency without/with MPS using the exact frozen training source and an existing training interpreter. It records aggregate completed iterations per second, estimated environment steps per second (24 task steps per iteration), wall time, per-job TensorBoard iteration metrics, peak total GPU memory and incremental memory. A failed process invalidates throughput. Provision sufficient memory first; the tool stops its clients gracefully if free memory crosses the reserve. Repeat with different environment counts and orders; external workloads and cache warmup confound a single pair. Set the scheduler's memory profile from measured peak usage with additional headroom, not from a claimed universal MPS speedup.
