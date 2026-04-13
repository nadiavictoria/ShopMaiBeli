"""
vLLM serving config for ShopMaiBeli workflow generator.

Serves the fine-tuned Qwen2.5-3B + LoRA adapter via vLLM's
OpenAI-compatible API on port 8000.

Usage (on Vast.ai with the trained adapter):
    pip install vllm
    python models/serve.py \
        --adapter_path models/checkpoints/shopmaibeli-sft \
        --port 8000

The backend then points SFT_MODEL_URL=http://<host>:8000 in backend/.env.

Alternatively, run directly with vllm CLI:
    vllm serve Qwen/Qwen2.5-3B-Instruct \
        --enable-lora \
        --lora-modules shopmaibeli-sft=./models/checkpoints/shopmaibeli-sft \
        --port 8000
"""

import argparse
import subprocess
import sys


def parse_args():
    parser = argparse.ArgumentParser(description="Serve the ShopMaiBeli SFT model via vLLM")
    parser.add_argument("--base_model", default="Qwen/Qwen2.5-3B-Instruct",
                        help="HuggingFace base model ID")
    parser.add_argument("--adapter_path", default="models/checkpoints/shopmaibeli-sft",
                        help="Path to the LoRA adapter directory (output of train.py)")
    parser.add_argument("--model_name", default="shopmaibeli-sft",
                        help="Name to register the adapter under (used in API calls)")
    parser.add_argument("--port", type=int, default=8000,
                        help="Port to serve on")
    parser.add_argument("--max_model_len", type=int, default=4096,
                        help="Maximum sequence length")
    parser.add_argument("--gpu_memory_utilization", type=float, default=0.90,
                        help="Fraction of GPU memory to use")
    parser.add_argument("--max_lora_rank", type=int, default=64,
                        help="Maximum LoRA rank allowed by the vLLM server")
    return parser.parse_args()


def serve(args):
    try:
        import vllm  # noqa: F401
    except ImportError:
        print("[serve] ERROR: vllm not installed. Run: pip install vllm", file=sys.stderr)
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "vllm.entrypoints.openai.api_server",
        "--model", args.base_model,
        "--enable-lora",
        "--lora-modules", f"{args.model_name}={args.adapter_path}",
        "--max-lora-rank", str(args.max_lora_rank),
        "--port", str(args.port),
        "--max-model-len", str(args.max_model_len),
        "--gpu-memory-utilization", str(args.gpu_memory_utilization),
        "--dtype", "bfloat16",
        "--trust-remote-code",
    ]

    print(f"[serve] Starting vLLM server on port {args.port}")
    print(f"[serve] Base model: {args.base_model}")
    print(f"[serve] LoRA adapter: {args.adapter_path} → {args.model_name}")
    print(f"[serve] Set SFT_MODEL_URL=http://0.0.0.0:{args.port} in backend/.env")
    print()

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n[serve] Stopped.")


if __name__ == "__main__":
    args = parse_args()
    serve(args)
