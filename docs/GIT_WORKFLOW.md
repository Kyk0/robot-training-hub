# Git workflow

The platform uses the `main` branch. Its Python/TypeScript source, tests, documentation, deployment templates, `uv.lock`, and npm lockfile are versioned. Runtime data, email outboxes, worker tokens, local environments, generated bundles, caches and built frontend assets are ignored.

The upstream training repositories are Git submodules pinned to the inspected revisions:

- `vendor/booster_mjlab`: `d92e11395d961096d639446c0a8a176f12bb51da`
- `vendor/mjlab`: `b517e0c489139e7fcee95702cfb2b01931264985`

Keep these pins stable during the workshop. The snapshot service rejects uncommitted tracked changes inside either training submodule. Platform changes belong in this repository; reviewed training changes belong in the appropriate training repository, followed by an explicit submodule-pointer commit here.

For a new development checkout after a remote has been configured:

```bash
git clone --recurse-submodules <your-repository-url> robot-training-hub
cd robot-training-hub
./scripts/bootstrap.sh
```

If the clone was made without submodules:

```bash
git submodule update --init --recursive
```

A normal change:

```bash
git switch -c feature/your-change
# Edit the relevant source files.
uv run pytest -q
npm run build --prefix frontend
git diff
git add <changed-files>
git commit -m "Describe the behavior changed"
```

Before workshop deployment, finish or reconcile active jobs, rebuild the frontend, commit the reviewed changes, and run `./scripts/copy-workers.sh` to refresh the three deployment copies. That script deploys files and leaves runtime data on its host. It does not automatically merge Git histories. Once a shared remote exists, update server repositories with `git pull --ff-only` and rebuild/install as needed instead of editing deployed files independently.

No hosting provider or public repository is created automatically. To attach a repository you own:

```bash
git remote add origin <your-repository-url>
git push -u origin main
```

The server repositories share the same `main` history, updated by fast-forward from the organizer's Git bundle. Their training submodules are intentionally uninitialized because workers use each host's existing training interpreter and receive frozen source from the coordinator. Run `git submodule update --init --recursive` there only if using that copy as a coordinator or development checkout.

`data/robot-training-hub.bundle` is an offline backup of the platform's current Git history, refreshed during deployment. Runtime data and upstream submodule object histories are not included. The upstream URLs and exact revisions are recorded in `.gitmodules` and the main repository's gitlinks.
