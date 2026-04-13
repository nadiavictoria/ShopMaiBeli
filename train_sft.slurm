#!/bin/bash
#SBATCH --job-name=shop-sft
#SBATCH --gpus=a100-40
#SBATCH --time=03:00:00
#SBATCH --output=train-%j.log

set -euo pipefail

cd "$HOME/ShopMaiBeli"
source .venv/bin/activate

python -V
which python

python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
python -c "import transformers, peft, trl, datasets, accelerate; print('training deps ok')"

mkdir -p models/checkpoints

python models/train.py \
  --data_dir data/workflows/train.jsonl \
  --output_dir models/checkpoints/shopmaibeli-sft \
  --epochs 3 \
  --strict_validation \
  --seed 42
