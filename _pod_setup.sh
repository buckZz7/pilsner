#!/usr/bin/env bash
# Pilsner ladder pod setup: tools, CUDA 12.8, repos, llama.cpp (sm_120), models.
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
export PATH=/root/.local/bin:$PATH

echo "=== [1/7] apt tools ==="
apt-get update -qq
apt-get install -y -qq cmake build-essential jq > /tmp/apt.log 2>&1 || tail -5 /tmp/apt.log

echo "=== [2/7] uv ==="
curl -LsSf https://astral.sh/uv/install.sh | sh

echo "=== [3/7] CUDA 12.8 toolkit (NVIDIA apt repo) ==="
OSVER=$(grep -oP '(?<=VERSION_ID=")[0-9.]+' /etc/os-release | tr -d '.')
curl -fsSL "https://developer.download.nvidia.com/compute/cuda/repos/ubuntu${OSVER}/x86_64/cuda-keyring_1.1-1_all.deb" -o /tmp/cuda-keyring.deb
dpkg -i /tmp/cuda-keyring.deb
apt-get update -qq
apt-get install -y -qq cuda-toolkit-12-8 > /tmp/cuda.log 2>&1 || tail -8 /tmp/cuda.log
ls /usr/local/cuda-12.8/bin/nvcc && /usr/local/cuda-12.8/bin/nvcc --version | tail -2

echo "=== [4/7] repos ==="
cd /root
git clone -q https://github.com/sierra-research/tau2-bench
git clone -q https://github.com/buckZz7/pilsner
cd /root/tau2-bench && uv sync 2>&1 | tail -2

echo "=== [5/7] llama.cpp build (sm_120) ==="
cd /root
git clone -q https://github.com/ggml-org/llama.cpp
cd /root/llama.cpp
export CUDACXX=/usr/local/cuda-12.8/bin/nvcc
export PATH=/usr/local/cuda-12.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:${LD_LIBRARY_PATH:-}
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_COMPILER=$CUDACXX -DCMAKE_CUDA_ARCHITECTURES=120 -DCMAKE_BUILD_TYPE=Release > /tmp/cmake.log 2>&1 || tail -10 /tmp/cmake.log
cmake --build build -j "$(nproc)" --target llama-server llama-quantize > /tmp/build.log 2>&1 || tail -15 /tmp/build.log
ls -la build/bin/llama-server build/bin/llama-quantize

echo "=== [6/7] model downloads ==="
python3 -m pip install -q -U "huggingface_hub[cli]" 2>&1 | tail -1
mkdir -p /root/models
cd /root/models
hf download prism-ml/Bonsai-27B-gguf Bonsai-27B-Q1_0.gguf --local-dir bonsai-1bit
hf download prism-ml/Ternary-Bonsai-27B-gguf Ternary-Bonsai-27B-Q2_0.gguf --local-dir bonsai-ternary
hf download Smoffyy/Qwen3.6-27B-Instruct-Revised-GGUF Qwen3.6-27B-Revised-q8_0.gguf --local-dir qwen36-q8
hf download unsloth/Qwen3-4B-GGUF Qwen3-4B-Q8_0.gguf --local-dir qwen3-4b
# IQ1 cliff-pinning rungs (mradermacher .i1- naming convention)
hf download mradermacher/Qwen3.6-27B-i1-GGUF --include "*.i1-IQ1_S*" --local-dir qwen36-iq1s
hf download mradermacher/Qwen3.6-27B-i1-GGUF --include "*.i1-IQ1_M*" --local-dir qwen36-iq1m
ls -la /root/models/*/

echo "=== [7/7] 2-bit rung (pre-made UD-IQ2_XXS; self-quantize from q8_0 is disabled) ==="
mkdir -p /root/models/qwen36-iq2xxs
hf download unsloth/Qwen3.6-27B-GGUF --include "*UD-IQ2_XXS*" --local-dir /root/models/qwen36-iq2xxs
ls -la /root/models/qwen36-iq2xxs/

echo "SETUP_DONE"
