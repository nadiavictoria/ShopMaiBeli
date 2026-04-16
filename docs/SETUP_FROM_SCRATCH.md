# Setup From Scratch

This guide is the end-to-end setup path for the current codebase. It covers:

1. local project setup
2. local app startup
3. GPU-cluster training with `train_sft.slurm`
4. serving the trained adapter on a GPU node
5. tunneling the model back to your laptop
6. wiring the local app to the served SFT model

It is based on the current checked-in implementation in:

- `backend/main.py`
- `backend/workflow_generator.py`
- `frontend/app.py`
- `models/train.py`
- `models/serve.py`
- `train_sft.slurm`

## Overview

The current runtime chain is:

```text
Chainlit frontend -> FastAPI backend -> workflow generation

workflow generation fallback order:
1. SFT model via SFT_MODEL_URL
2. DeepSeek via DEEPSEEK_API_KEY
3. workflows/example_shopping.json
```

That means:

- you can run the app locally without the SFT model
- once the GPU-hosted SFT server is available, the backend will use it first
- DeepSeek remains the fallback generator if SFT is unavailable or invalid

## Part 1: Clone The Repo Locally

On your local machine:

```bash
git clone <repo-url> ShopMaiBeli
cd ShopMaiBeli
```

## Part 2: Create The Local Python Environment

From the project root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
```

If you want to run the async test suite locally, install the missing plugin too:

```bash
python -m pip install pytest-asyncio
```

## Part 3: Configure Local Environment Variables

Create `backend/.env`.

If you only want the app to run locally before SFT is ready:

```bash
cat > backend/.env <<'EOF'
DEEPSEEK_API_KEY=your_key_here
EOF
```

If you already have a served SFT model or will add it later:

```bash
cat > backend/.env <<'EOF'
SFT_MODEL_URL=http://localhost:8001
DEEPSEEK_API_KEY=your_key_here
EOF
```

Notes:

- `backend/main.py` loads `backend/.env` first, then project-root `.env`
- `SFT_MODEL_URL` must point to an OpenAI-compatible vLLM server
- the backend expects the served LoRA model name to be `shopmaibeli-sft`

## Part 4: Run The App Locally

From the project root:

```bash
source .venv/bin/activate
./start.sh
```

This starts:

- backend on `http://localhost:8888`
- frontend on `http://localhost:8000`

Verify the backend:

```bash
curl http://localhost:8888/health
```

Expected:

```json
{"status":"ok"}
```

Open the frontend:

```text
http://localhost:8000
```

Useful current behavior:

- normal chat messages default to `run_workflow`
- `get_workflow` generates a workflow and returns an editor link
- `run_workflow` streams NDJSON execution events back to the UI

Stop the app when needed:

```bash
./stop.sh
```

## Part 5: Prepare The GPU Cluster Copy

The current `train_sft.slurm` assumes:

- the repo lives at `~/ShopMaiBeli`
- the training virtualenv is `~/ShopMaiBeli/.venv`

You should mirror that layout on the cluster to avoid editing the script.

### 5.1 Copy The Repo To The Cluster

From your local machine:

```bash
rsync -av ./ nadia@xgph16:~/ShopMaiBeli/
```

If you connect through a login node or different hostname, replace `xgph16`
with the correct host.

### 5.2 SSH Into The Cluster

```bash
ssh nadia@xgph16
cd ~/ShopMaiBeli
```

### 5.3 Create The Training Environment On The Cluster

Inside `~/ShopMaiBeli` on the cluster:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install torch transformers peft trl datasets accelerate bitsandbytes vllm
```

Why the extra install is needed:

- `requirements.txt` covers the app dependencies
- training and serving dependencies are not fully included there

### 5.4 Sanity Check The Training File

The current trainer expects:

```text
data/workflows/train.jsonl
```

Verify it exists on the cluster:

```bash
ls data/workflows/train.jsonl
```

## Part 6: Submit The SFT Training Job

The current SLURM script is:

```text
train_sft.slurm
```

It currently requests:

- job name `shop-sft`
- GPU `a100-40`
- time `03:00:00`
- output log `train-%j.log`

### 6.1 Check Whether Your Cluster Uses Different SLURM Syntax

Before submitting, read the header:

```bash
sed -n '1,40p' train_sft.slurm
```

If your cluster requires any of the following, edit the file first:

- a different GPU resource syntax
- a `--partition`
- a `--account`
- a longer wall time
- a different repo path than `~/ShopMaiBeli`

The current script body expects:

```bash
cd "$HOME/ShopMaiBeli"
source .venv/bin/activate
```

If your cluster path is different, update those lines before submission.

### 6.2 Submit The Job

```bash
sbatch train_sft.slurm
```

### 6.3 Monitor The Job

```bash
squeue -u nadia
```

Once the job starts, tail the log:

```bash
tail -f train-<jobid>.log
```

You want to see:

- Python version output
- CUDA available as `True`
- a visible GPU device name
- `training deps ok`
- training progress from `models/train.py`

### 6.4 Training Output Location

The current script saves the adapter to:

```text
models/checkpoints/shopmaibeli-sft
```

That directory should contain the LoRA adapter and `training_metadata.json`.

## Part 7: Request An Interactive GPU Allocation

If you want to debug, train manually, or serve the model from an interactive GPU
session instead of a batch job, use your cluster's working interactive command:

```bash
srun --gpus=a100-40 --time=03:00:00 --pty bash
```

If your cluster requires additional flags, the common variants are:

```bash
srun --gpus=a100-40 --time=03:00:00 --partition=<partition> --pty bash
```

```bash
srun --gpus=a100-40 --time=03:00:00 --account=<account> --pty bash
```

```bash
srun --gpus=a100-40 --time=03:00:00 --partition=<partition> --account=<account> --pty bash
```

Once the interactive shell starts, check the assigned node with:

```bash
echo "$SLURM_JOB_ID"
echo "$SLURMD_NODENAME"
```

Then activate the environment:

```bash
cd ~/ShopMaiBeli
source .venv/bin/activate
```

Sanity check the GPU:

```bash
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

From that interactive allocation, you can run training manually:

```bash
python models/train.py \
  --data_dir data/workflows/train.jsonl \
  --output_dir models/checkpoints/shopmaibeli-sft \
  --epochs 3 \
  --strict_validation \
  --seed 42
```

Or start the SFT server manually:

```bash
python models/serve.py \
  --adapter_path models/checkpoints/shopmaibeli-sft \
  --port 8001
```

If `srun --gpus=a100-40 --time=03:00:00 --pty bash` does not work on your
cluster,
compare it with whatever resource syntax your cluster expects in working SLURM
examples. Some clusters want a different GPU flag format or require
`--partition` and `--account`.

## Part 8: Serve The Trained Adapter On The GPU Cluster

After training finishes, stay on a GPU-capable machine and activate the same
environment:

```bash
cd ~/ShopMaiBeli
source .venv/bin/activate
```

You have two supported serving paths.

### Option A: Use The Helper Script

```bash
python models/serve.py \
  --adapter_path models/checkpoints/shopmaibeli-sft \
  --port 8001
```

### Option B: Use vLLM Directly

```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-3B-Instruct \
  --enable-lora \
  --lora-modules shopmaibeli-sft=models/checkpoints/shopmaibeli-sft \
  --max-lora-rank 64 \
  --port 8001 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.9 \
  --dtype bfloat16 \
  --trust-remote-code
```

### 7.1 Verify The Served Model

From another shell that can reach the serving host:

```bash
curl http://<gpu-host>:8001/v1/models
```

You should see `shopmaibeli-sft` in the served models list.

## Part 9: Tunnel The GPU Model Back To Your Laptop

If the GPU host is not directly reachable from your laptop, create an SSH
tunnel.

Example:

```bash
ssh -L 8001:<gpu-host>:8001 your_soc_unix_id@xlogin.comp.nus.edu.sg
```

Keep that SSH session open.

Then verify from your laptop:

```bash
curl http://localhost:8001/v1/models
```

## Part 10: Point The Local App At The Cluster-Hosted SFT Model

On your local machine, update `backend/.env`:

```bash
cat > backend/.env <<'EOF'
SFT_MODEL_URL=http://localhost:8001
DEEPSEEK_API_KEY=your_key_here
EOF
```

Restart the app:

```bash
./stop.sh
./start.sh
```

## Part 11: Confirm The App Uses SFT

Watch the backend log locally:

```bash
tail -n 100 backend.log
```

Then send a query in the frontend.

Current expected success path:

```text
[generate_workflow] SFT model succeeded
```

Other possible current paths:

```text
[generate_workflow] DeepSeek fallback succeeded
[generate_workflow] Using hardcoded fallback workflow
```

If SFT is returning malformed output, the backend also writes raw responses to:

```text
artifacts/sft_debug/latest_raw_response.txt
```

## Part 12: Optional Validation Steps

### 11.1 Probe The Served SFT Model Directly

With the tunnel or direct network path available:

```bash
python scripts/probe_sft_outputs.py \
  --base-url http://localhost:8001 \
  --model shopmaibeli-sft \
  --output output/sft_probe_results.jsonl
```

This helps validate:

- raw JSON discipline
- parse success
- workflow schema validity

### 11.2 Inspect Active Backend Sessions

```bash
curl http://localhost:8888/sessions
```

### 11.3 Run The Local Test Suite

Non-integration:

```bash
source .venv/bin/activate
python -m pytest tests -m "not integration"
```

Integration:

```bash
python -m pytest tests -m integration
```

Current caveat:

- install `pytest-asyncio` first or async tests will fail to run cleanly

## Part 13: Common Failure Points

### `sbatch` job starts but immediately fails

Check:

- `~/ShopMaiBeli` actually exists on the cluster
- `.venv` exists inside that repo
- training dependencies were installed in that environment
- `data/workflows/train.jsonl` exists

### `train_sft.slurm` requests the wrong GPU resource

Your cluster may not accept:

```text
#SBATCH --gpus=a100-40
```

If that syntax is wrong for your environment, edit the SLURM header before
submitting.

### `srun --pty bash` is rejected or the resource flags are wrong

Check:

- whether your cluster wants `--partition`
- whether your cluster wants `--account`
- whether the GPU request format differs from `--gpus=a100-40`
- whether the login node allows interactive GPU allocations directly

### SFT server comes up but the app still uses fallback

Check:

- `curl http://localhost:8001/v1/models`
- `backend/.env` really contains `SFT_MODEL_URL=http://localhost:8001`
- the SSH tunnel is still open
- `backend.log` for SFT errors

### DeepSeek fallback is failing too

Check:

- `DEEPSEEK_API_KEY` is present in `backend/.env`
- the key is valid
- outbound network access is available from the machine running the backend

### The frontend works but the workflow editor link fails

Check:

- backend is running on `http://localhost:8888`
- `BACKEND_URL` is not overridden incorrectly
- you generated a workflow in the same active session before opening the editor

## Recommended Order If You Are Starting Fresh

1. Get the app running locally with `DEEPSEEK_API_KEY` only.
2. Copy the repo to the cluster.
3. Create the cluster `.venv` and install training dependencies.
4. Submit `train_sft.slurm`.
5. If needed, use `srun --gpus=a100-40 --time=03:00:00 --pty bash` for a
   3-hour interactive GPU session.
6. Serve the trained adapter on port `8001`.
7. Tunnel port `8001` back to your laptop.
8. Set `SFT_MODEL_URL=http://localhost:8001`.
9. Restart the app and confirm `SFT model succeeded` in `backend.log`.
