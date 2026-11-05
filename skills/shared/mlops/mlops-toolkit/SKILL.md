---
name: mlops-toolkit
description: "Run local ML inference, evaluations, and tracking."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [mlops, llm, inference, evaluation, huggingface]
---

# MLOps Toolkit

Use the reference matching the concrete task. These are task-specific examples, not a fixed/current API or hardware guarantee: check the installed tool's `--help`, official docs, model card/license, actual GPU/VRAM, and provider access before running or recommending a command. Use a project venv or an approved package manager for Python installs, not bare system `pip`.

## When to Use / Reference

| Task | Read |
|---|---|
| Find/download/publish Hub models and datasets with the current `hf` CLI | `references/huggingface-hub.md` |
| Select GGUF quants, discover repository files, run llama.cpp | `references/llama-cpp.md` |
| Serve/batch LLMs with vLLM | `references/serving-llms-vllm.md` |
| Run reproducible harness evaluations | `references/evaluating-llms-harness.md` |
| Compare published model benchmarks and costs at matched effort | `references/model-benchmark-comparisons.md` |
| Track runs and artifacts with Weights & Biases | `references/weights-and-biases.md` |
| Generate audio with AudioCraft, or segment images with SAM | `references/audiocraft-audio-generation.md`, `references/segment-anything-model.md` |

## Procedure

1. Identify the actual workload and read **only its reference**. Verify the current project environment and model/license constraints before installing or downloading large weights.
2. Use actual tool output for model availability, GPU capacity, runtime behavior, and benchmark results; label older recipe numbers as examples, not measurements on this host. Do not place tokens in command lines, logs, or example scripts.
3. Execute a small end-to-end probe in the user-approved environment and capture its output. For a provider/model routing choice, use matched quality, cost-per-task, tokens-per-task, and a pilot on the user's real workload; benchmarks alone do not authorize a route change.

## Pitfalls

- A reference's copied model ID or performance/VRAM estimate can go stale; recheck the live source.
- Some upstream reference sections once linked to unbundled child files; this copy removes those dead links. Use the upstream project docs for omitted advanced topics.
- Installing GPU packages or invoking a paid endpoint has side effects; confirm the user's environment and cost scope first.

## Verification

- [ ] Exact model/dependency/version and capacity assumptions checked on the target environment.
- [ ] A real run or current cited source backs every operational conclusion.
- [ ] Every documented local reference exists; no credential, paid call, or routing change was assumed.
