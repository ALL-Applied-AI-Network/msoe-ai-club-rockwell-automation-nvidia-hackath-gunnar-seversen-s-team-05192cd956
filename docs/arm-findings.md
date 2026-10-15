# Can the starter run on the DGX Spark (ARM)?

Checked Oct 15, 2026. The DGX Spark uses an **aarch64** (64-bit ARM) CPU with a GB10 Blackwell GPU. Most prebuilt Python packages and GPU software are made for **x86_64** (Intel/AMD) first, so we checked every piece the starter needs.

## Verdict

**Nothing in the software stack blocks the Spark.** Every package has an official aarch64 build. The real risks are:

- **the GPU driver version.** Isaac Sim 6.0 needs the R580 driver branch, and a newer driver crashes it;
- **Cosmos3-Nano has never been tested on GB10 or on the L40S.**

**Recommendation: do the first end-to-end run on Brev (x86_64, L40S).** That's the platform closest to the starter's validated setup (Linux x86, RTX A6000). Run on the Spark once Brev has given us a known-good reference. If the Spark then fails, we'll know the platform is the cause, not our setup.

## Component by component

| Component | aarch64 support | Evidence |
|---|---|---|
| Isaac Sim 6.0 | **Yes, but only on DGX Spark**, DGX OS 7, driver 580.142 (tested). cuRobo and cuMotion are not supported there; the starter uses neither. | [Isaac Sim 6.0 requirements](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/requirements.html) |
| Isaac Sim pip wheels | Yes: `isaacsim_kernel-6.0.0.1-cp312-none-manylinux_2_35_aarch64.whl` is on pypi.nvidia.com. Some modules may need `libgomp` preloaded on Spark; our `scripts/gpu_setup.sh` does this. | Read directly from https://pypi.nvidia.com/isaacsim-kernel/; [Python install docs](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/install_python.html) |
| Isaac Sim container | Multi-arch: the same tag runs on x86_64 and aarch64 | [Container install docs](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/installation/install_container.html) |
| GPU driver | **Risk.** NVIDIA staff confirmed Isaac Sim 6.0.x crashes on Spark with driver 595.x. The fix is driver 580.159.03 (R580), installed with the DGX Spark Dashboard's "Update" button, *not* the generic x86 driver download. | [NVIDIA forum thread, Jul 2026](https://forums.developer.nvidia.com/t/isaac-sim-6-0-1-gpu-crash-on-dgx-spark-gb10-arm64-driver-595-71-05/376418) |
| PyTorch 2.11 (CUDA 13) | Yes: `torch-2.11.0+cu130-cp312-...-manylinux_2_28_aarch64.whl` and `torchvision-0.26.0+cu130` aarch64 | Read directly from https://download.pytorch.org/whl/cu130/ |
| `transformers` 5.9.0, `transformers-cosmos3` | Pure Python, so any platform. `transformers-cosmos3` 0.1.0 needs only `transformers>=4.57` and Python 3.10 or later. | [cosmos-framework `packages/transformers-cosmos3`](https://github.com/nvidia/cosmos-framework/tree/main/packages/transformers-cosmos3) |
| Cosmos3-Nano weights | Platform-independent files. The model card lists Ampere, Hopper and Blackwell GPUs as supported, tested on GB200 and H100, Linux only, BF16 only. **GB10 and the L40S (an Ada-generation GPU) are not listed as tested.** | [Model card](https://huggingface.co/nvidia/Cosmos3-Nano) |
| `requirements.txt` / `requirements-cosmos.txt` (numpy, scipy, opencv-python-headless, imageio-ffmpeg) | Yes: all four have aarch64 wheels in their current releases | Read directly from the PyPI JSON API |
| FANUC ER-4iA robot asset | Downloaded from NVIDIA's asset server at runtime; plain data, so platform-independent. It needs Isaac Sim 6.0 (`scene_config.py`). | `fanuc_er4ia_sim/scene_config.py:21` |

## What to check first on the Spark

1. `nvidia-smi` shows a **580.x** driver. If it shows 595 or newer, update through the DGX Spark Dashboard before installing anything.
2. `scripts/gpu_setup.sh` step 7 passes. That proves CUDA works in the Cosmos environment, Cosmos3-Nano loads, and Isaac Sim builds the scene with the robot.
3. One reference run (seed 20261009) gives the same result as on Brev.

## Other notes

- The Spark has 128 GB of memory shared between CPU and GPU. Cosmos3-Nano needs about 16–17 GB for the reasoning part, according to [NVIDIA's cookbook](https://github.com/NVIDIA/cosmos/blob/main/cookbooks/cosmos3/reasoner/README.md). Memory is not a concern on either machine.
- Community guides report Isaac Sim working on the Spark, but they built it from source. The official pip and container route is newer and less reported. The CSI and UWM Spark admins may already have Isaac Sim installed; ask them which version and which driver.
