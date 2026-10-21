#!/usr/bin/env bash
#SBATCH --job-name=robot-workshop
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
# Set partition/account/reservation according to your institution before sbatch.
set -euo pipefail
cd /srv/robot-training-hub
set -a
source /etc/robot-hub/worker.env
set +a
exec .venv/bin/robot-worker
