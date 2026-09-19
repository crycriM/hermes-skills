---
name: mlops-inference
description: "LLM inference serving and benchmarking: llama.cpp, vLLM, TensorRT-LLM, GGUF, Outlines, Guidance, Instructor, Obliteratus, and benchmarking tools."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [MLOps, Inference, LLM, Serving, Benchmarking, GGUF, llama.cpp, vLLM, TensorRT, Outlines, Guidance]
    related_skills: [mlops-training, mlops-model-manager, mlops-vector-databases]
---

# MLOps Inference

LLM inference serving, quantization, and benchmarking across multiple frameworks.

## 1. llama.cpp

CPU inference on Apple Silicon, non-NVIDIA GPUs, and embedded devices. GGUF format, quantization, edge deployment.

See: `references/llama-cpp.md`

## 2. llama.cpp Benchmarking

Benchmarking tools for llama.cpp performance measurement.

See: `references/llama-cpp-benchmark.md`

## 3. vLLM

High-throughput LLM serving with vLLM. PagedAttention, continuous batching.

See: `references/vllm.md`

## 4. TensorRT-LLM

NVIDIA TensorRT-LLM for GPU-accelerated inference.

See: `references/tensorrt-llm.md`

## 5. GGUF Utilities

GGUF format utilities including vision check.

See: `references/gguf.md`
See: `references/gguf-vision-check.md`

## 6. Structured Output

- **Outlines**: Structured JSON/schema generation with LLMs
- **Guidance**: Controllable generation with guidance patterns
- **Instructor**: Typed structured output for LLMs
- **Obliteratus**: Context window management

See: `references/outlines.md`
See: `references/guidance.md`
See: `references/instructor.md`
See: `references/obliteratus.md`
