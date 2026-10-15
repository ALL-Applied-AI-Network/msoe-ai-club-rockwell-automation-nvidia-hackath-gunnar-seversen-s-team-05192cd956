#!/usr/bin/env bash
# Prepare a fresh Brev (x86_64) or DGX Spark (aarch64) GPU machine to run the
# fanuc_er4ia_sim starter. Read docs/gpu-runbook.md first.
#
#   export OMNI_KIT_ACCEPT_EULA=YES     # only after reading the Isaac Sim EULA
#   export HF_TOKEN=...                 # optional; never commit it
#   scripts/gpu_setup.sh
#
# Safe to rerun: finished steps are skipped. Everything goes under $WORK.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
STARTER="$REPO/fanuc_er4ia_sim"
WORK="${WORK:-$HOME/fanuc-gpu}"
ISAAC_PIP_VERSION="6.0.0.1"
TORCH_VERSION="2.11.0"
TORCHVISION_VERSION="0.26.0"
TORCH_INDEX="${TORCH_INDEX:-https://download.pytorch.org/whl/cu130}"
TRANSFORMERS_VERSION="5.9.0"  # transformers-cosmos3's own uv.lock
COSMOS_FRAMEWORK_REV="7cfaf7854b2114eda5deb36250a7e8f00c64d69e"  # 2026-10-12
COSMOS3_NANO_REVISION="e59a53c25979a090fa8706c9acc0c254a6e89b92"  # 2026-09-16
MODEL_DIR="${COSMOS3_NANO_PATH:-$WORK/models/Cosmos3-Nano}"
COSMOS_VENV="$WORK/cosmos-venv"
COSMOS="$COSMOS_VENV/bin/python"

step() { printf '\n== %s\n' "$*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

mkdir -p "$WORK"

step "1/7 Machine check"
ARCH="$(uname -m)"
command -v nvidia-smi >/dev/null || die "nvidia-smi not found: this machine has no NVIDIA driver"
GPU="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1)"
DRIVER="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)"
echo "arch=$ARCH  gpu=$GPU  driver=$DRIVER"
case "$DRIVER" in
    580.*) ;;
    *) echo "WARNING: Isaac Sim 6.0 is tested on the R580 driver branch. Driver $DRIVER" \
            "may crash its RTX renderer; see docs/gpu-runbook.md, 'Driver'." ;;
esac
FREE_GB="$(df -Pk "$WORK" | awk 'NR==2 {print int($4 / 1048576)}')"
[ "$FREE_GB" -ge 100 ] || die "Need about 100 GB free under $WORK; only ${FREE_GB} GB available"
if ! command -v uv >/dev/null; then
    python3 -m pip install --user uv || die "Install uv (https://docs.astral.sh/uv/) and rerun"
    export PATH="$HOME/.local/bin:$PATH"
fi

step "2/7 Isaac Sim 6.0"
if [ -n "${ISAAC:-}" ] && [ -x "$ISAAC/python.sh" ]; then
    echo "Using existing Isaac Sim at $ISAAC"
else
    [ "${OMNI_KIT_ACCEPT_EULA:-}" = "YES" ] \
        || die "Read the Isaac Sim EULA (docs/gpu-runbook.md), then: export OMNI_KIT_ACCEPT_EULA=YES"
    ISAAC="$WORK/isaacsim"
    if [ ! -x "$ISAAC/venv/bin/python" ]; then
        uv venv --seed --python 3.12 "$ISAAC/venv"
        "$ISAAC/venv/bin/python" -m pip install "torch==$TORCH_VERSION" --index-url "$TORCH_INDEX"
        "$ISAAC/venv/bin/python" -m pip install "isaacsim[all,extscache]==$ISAAC_PIP_VERSION" \
            --extra-index-url https://pypi.nvidia.com
    fi
    # The starter calls "$ISAAC/python.sh", which only a standalone install has.
    cat > "$ISAAC/python.sh" <<EOF
#!/usr/bin/env bash
# Stand-in for a standalone install's python.sh, for pip-installed Isaac Sim.
export OMNI_KIT_ACCEPT_EULA=YES
if [ "\$(uname -m)" = "aarch64" ]; then
    # Isaac Sim docs: some modules need libgomp preloaded on DGX Spark.
    gomp="\$(ldconfig -p | awk '/libgomp.so.1 /{print \$NF; exit}')"
    [ -n "\$gomp" ] && export LD_PRELOAD="\$gomp\${LD_PRELOAD:+:\$LD_PRELOAD}"
fi
exec "$ISAAC/venv/bin/python" "\$@"
EOF
    chmod +x "$ISAAC/python.sh"
fi
ISAAC_VERSION="$("$ISAAC/python.sh" -c 'from importlib.metadata import version; print(version("isaacsim"))' 2>/dev/null \
    || cat "$ISAAC/VERSION" 2>/dev/null || echo unknown)"
echo "Isaac Sim version: $ISAAC_VERSION"
case "$ISAAC_VERSION" in
    6.0*) ;;
    *) die "Isaac Sim 6.0 required (the ER-4iA robot asset ships only with 6.0); found '$ISAAC_VERSION'." \
           "Unset ISAAC to install 6.0 with pip under $WORK." ;;
esac

step "3/7 Cosmos environment (torch, transformers, transformers-cosmos3)"
if [ ! -x "$COSMOS" ]; then
    uv venv --seed --python 3.12 "$COSMOS_VENV"
fi
"$COSMOS" -m pip install "torch==$TORCH_VERSION" "torchvision==$TORCHVISION_VERSION" --index-url "$TORCH_INDEX"
"$COSMOS" -m pip install "transformers==$TRANSFORMERS_VERSION" accelerate huggingface_hub
"$COSMOS" -m pip install \
    "transformers-cosmos3 @ git+https://github.com/nvidia/cosmos-framework.git@$COSMOS_FRAMEWORK_REV#subdirectory=packages/transformers-cosmos3"
"$COSMOS" -m pip install -r "$STARTER/requirements-cosmos.txt"

step "4/7 Cosmos3-Nano weights (about 35 GB)"
if [ -f "$MODEL_DIR/config.json" ] && [ -f "$MODEL_DIR/model.safetensors.index.json" ]; then
    echo "Weights already in $MODEL_DIR"
else
    # HF_TOKEN, if set, is read from the environment by the hf CLI.
    "$COSMOS_VENV/bin/hf" download nvidia/Cosmos3-Nano --revision "$COSMOS3_NANO_REVISION" \
        --local-dir "$MODEL_DIR" --exclude "assets/*" --exclude "images/*"
fi

step "5/7 Host environment and 34 host tests"
[ -x "$STARTER/.venv/bin/python" ] || uv venv --seed --python 3.12 "$STARTER/.venv"
"$STARTER/bootstrap.sh"

step "6/7 Environment file"
cat > "$WORK/env.sh" <<EOF
# source this before running the pipeline or harness
export ISAAC="$ISAAC"
export COSMOS="$COSMOS"
export COSMOS3_NANO_PATH="$MODEL_DIR"
EOF
echo "Wrote $WORK/env.sh"

step "7/7 Dependency checks from SETUP.md"
cd "$STARTER"
"$COSMOS" -c 'import torch, transformers, scipy, cv2; print("CUDA:", torch.cuda.is_available()); assert torch.cuda.is_available(), "no CUDA"'
COSMOS3_NANO_PATH="$MODEL_DIR" "$COSMOS" -c 'from perceive import load_model; model, processor = load_model(); print("Model ready")'
mkdir -p runs
rm -f runs/scene.usd
"$ISAAC/python.sh" build_scene.py --headless --save runs/scene.usd
[ -s runs/scene.usd ] || die "Scene build wrote no runs/scene.usd: check the robot asset (FANUC_ROBOT_USD) and the log above"

{
    echo "date_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "repo_commit: $(git -C "$REPO" rev-parse --short HEAD)"
    echo "arch: $ARCH"
    echo "gpu: $GPU"
    echo "driver: $DRIVER"
    echo "isaac: $ISAAC ($ISAAC_VERSION)"
    echo "cosmos_framework_rev: $COSMOS_FRAMEWORK_REV"
    echo "cosmos3_nano_revision: $COSMOS3_NANO_REVISION"
} > "$WORK/setup_record.txt"
"$COSMOS" -m pip freeze > "$WORK/freeze-cosmos.txt"
"$STARTER/.venv/bin/python" -m pip freeze > "$WORK/freeze-host.txt"
cat "$WORK/setup_record.txt"
echo
echo "Setup complete. Next: source $WORK/env.sh, then follow 'First run' in docs/gpu-runbook.md."
