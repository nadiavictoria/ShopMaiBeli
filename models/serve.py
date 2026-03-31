"""
vLLM serving script for the fine-tuned workflow generation model.
Exposes OpenAI-compatible /v1/chat/completions endpoint.

Usage (on Vast.ai):
    python models/serve.py --model models/checkpoints/ --port 8001

Then set in backend/.env:
    WORKFLOW_MODEL_URL=http://<vast-ai-ip>:8001
"""
import argparse
import subprocess
import sys


def serve(args):
    try:
        import vllm  # noqa
    except ImportError:
        print("vLLM not installed. Run: pip install vllm")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "vllm.entrypoints.openai.api_server",
        "--model", args.model,
        "--host", "0.0.0.0",
        "--port", str(args.port),
        "--max-model-len", "4096",
        "--dtype", "bfloat16"
    ]
    print(f"Starting vLLM server: {' '.join(cmd)}")
    subprocess.run(cmd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="Path to model or HuggingFace model ID")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    serve(args)
