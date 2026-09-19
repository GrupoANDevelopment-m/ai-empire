#!/usr/bin/env python3
"""
AI Empire Lite — runs on 4GB RAM, no GPU, no Docker.

Inspired by Project Colibrì's multitier philosophy:
- LLM (smallest viable) lives in RAM
- Everything else stays on disk and is loaded on demand
- The agent itself stays under 100MB
- Tools (Playwright, PIL) are loaded only when needed

Memory budget on 4GB RAM:
  OS + browser + apps:  ~1.5 GB
  Ollama (qwen2.5:0.5b): 0.5 GB
  Agent + Python deps:   0.3 GB
  Playwright (per-call): 0.5 GB
  -------------------------------
  Total:                  2.8 GB  ✓ fits in 4 GB

On 8GB RAM, upgrade to qwen2.5:3b.
On 16GB RAM, add ComfyUI quantized models.
On 32GB+ with GlM-5.2 + Colibrì, get a frontier LLM.
"""
import os
import sys
import json
import shutil
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LLMCLIENT = REPO_ROOT / "empire" / "agent" / "llm" / "client.py"
MODELS = {
    # model_tag : (size_gb, min_ram_gb, quant, description)
    "qwen2.5:0.5b":  (0.5,  4, "Q4_K_M", "Tiny smoke-test model, fastest on CPU"),
    "qwen2.5:1.5b":  (1.2,  6, "Q4_K_M", "Best quality/footprint for 8GB laptops"),
    "qwen2.5:3b":    (1.9,  8, "Q4_K_M", "Sweet spot for 16GB machines, very capable"),
    "qwen2.5:7b":    (4.5, 16, "Q4_K_M", "Strong reasoning, needs swap on 16GB"),
    "llama3.1:8b":   (4.7, 16, "Q4_K_M", "Meta flagship 8B"),
    "mistral:7b":    (4.1, 16, "Q4_K_M", "Mistral 7B instruct"),
    "phi4:mini":     (2.5,  8, "Q4_K_M", "Microsoft Phi-4 mini, very efficient"),
    "gemma3:1b":     (0.8,  4, "Q4_K_M", "Google Gemma 3 1B, smallest capable"),
}

def get_total_ram_gb() -> float:
    """Get total system RAM in GB."""
    try:
        out = subprocess.check_output(["free", "-g"], text=True)
        for line in out.splitlines():
            if line.startswith("Mem:"):
                return float(line.split()[1])
    except Exception:
        pass
    return 0


def has_docker() -> bool:
    return shutil.which("docker") is not None


def has_ollama() -> bool:
    return shutil.which("ollama") is not None


def has_gpu() -> bool:
    try:
        out = subprocess.check_output(["nvidia-smi", "-L"], stderr=subprocess.DEVNULL, text=True)
        return "GPU" in out
    except Exception:
        return False


def recommend_model(ram_gb: float) -> str:
    """Pick best model that fits in available RAM."""
    candidates = [(tag, *info) for tag, info in MODELS.items() if info[1] <= ram_gb]
    if not candidates:
        return "qwen2.5:0.5b"
    # Pick the largest model that fits (best quality)
    candidates.sort(key=lambda c: c[2], reverse=True)
    return candidates[0][0]


def command_install():
    """Install Ollama + recommended model."""
    ram_gb = get_total_ram_gb()
    recommended = recommend_model(ram_gb)
    docker = has_docker()
    gpu = has_gpu()
    print(f"Detected: {ram_gb:.0f} GB RAM · Docker: {docker} · GPU: {gpu}")
    print(f"Recommended model: {recommended} (~{MODELS[recommended][0]} GB, {MODELS[recommended][3]})")
    print()

    if not has_ollama():
        print("→ Installing Ollama...")
        if sys.platform == "darwin":
            print("   Run: brew install ollama")
        else:
            subprocess.run(["curl", "-fsSL", "https://ollama.ai/install.sh"], stdout=subprocess.DEVNULL)
            print("   Downloaded. Run: ollama serve &")
            print("   Then re-run: empire-lite install")
        return

    print(f"→ Pulling {recommended}...")
    subprocess.run(["ollama", "pull", recommended], check=False)
    print()
    print("✓ Done. Run: empire-lite chat")


def command_doctor():
    """Show the current state of the system."""
    ram_gb = get_total_ram_gb()
    recommended = recommend_model(ram_gb)
    print(f"\n  AI Empire Lite — system report")
    print(f"  ----------------------------------------")
    print(f"  RAM:           {ram_gb:.1f} GB")
    print(f"  CPU cores:     {os.cpu_count()}")
    print(f"  Docker:        {'yes' if has_docker() else 'NO (using lite mode)'}")
    print(f"  GPU:           {'yes' if has_gpu() else 'no'}")
    print(f"  Ollama:        {'installed' if has_ollama() else 'NOT installed'}")
    print(f"  Recommended:   {recommended} ({MODELS[recommended][0]} GB)")
    print()
    # Test that the agent can be imported
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from empire.agent.llm.client import LLMClient
        from empire.agent.llm.agent import EmpireAgent
        print(f"  Agent code:    OK (LLMClient, EmpireAgent)")
    except Exception as e:
        print(f"  Agent code:    ERROR — {e}")
    print()


def command_chat():
    """Start the agent REPL."""
    if not has_ollama():
        print("✗ Ollama not installed. Run: empire-lite install")
        sys.exit(1)
    # Start Ollama in background if not running
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=2)
        if r.status_code != 200:
            raise Exception("not running")
    except Exception:
        print("→ Starting Ollama...")
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(20):
            time.sleep(1)
            try:
                r = httpx.get("http://localhost:11434/api/tags", timeout=1)
                if r.status_code == 200:
                    break
            except Exception:
                pass

    sys.path.insert(0, str(REPO_ROOT))
    import asyncio
    from empire.agent.llm.client import LLMClient
    from empire.agent.llm.agent import EmpireAgent

    async def main():
        llm = LLMClient()
        info = await llm.detect()
        print(f"\n  AI Empire Lite · {info['backend']} · {info.get('model', '?')}")
        print(f"  RAM: {get_total_ram_gb():.0f} GB · Tools: 8")
        print(f"  Type 'quit' to exit.\n")
        if not llm.is_available:
            print("  ✗ LLM not reachable. Try: ollama serve")
            return
        agent = EmpireAgent(llm=llm)
        sess = "lite"
        while True:
            try:
                q = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nbye")
                return
            if not q:
                continue
            if q.lower() in ("quit", "exit", "q"):
                print("bye")
                return
            print("agent> ", end="", flush=True)
            async for c in agent.stream(q, session=sess):
                t = c["type"]
                if t == "text":
                    print(c["content"], end="", flush=True)
                elif t == "tool_call":
                    print(f"\n  [tool {c['tool']}({c['args']})]\n  ", end="", flush=True)
                elif t == "tool_result":
                    s = c["result"]
                    if len(s) > 200:
                        s = s[:200] + "..."
                    print(f"\n  [result: {s}]\n  ", end="", flush=True)
                elif t == "error":
                    print(f"\n  [error: {c['text'][:200]}]\n  ", end="", flush=True)
                elif t == "done":
                    print()
                    break

    asyncio.run(main())


def main():
    cmds = {
        "install": command_install,
        "doctor":  command_doctor,
        "chat":    command_chat,
        "info":    command_doctor,
    }
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        print()
        print("Commands:")
        print("  empire-lite doctor   — show what's available on this machine")
        print("  empire-lite install  — install Ollama + the right model for your RAM")
        print("  empire-lite chat     — talk to the agent (no Docker needed)")
        sys.exit(1)
    cmds[sys.argv[1]]()


if __name__ == "__main__":
    main()
