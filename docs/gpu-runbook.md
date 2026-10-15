# GPU runbook: from a fresh machine to the first measured run

This takes a GPU machine with nothing installed to one complete, timed run of the starter, and then to a sweep across the dev seeds. It works on **Brev** (rented cloud GPU, x86_64) and on the **DGX Spark** (ARM). Start on Brev; [arm-findings.md](arm-findings.md) explains why.

## Words used here

- **Isaac Sim**: NVIDIA's robot simulator. It renders the camera image (stage 1) and simulates the arm and gripper physically (stage 4). It has its own Python interpreter, called through `$ISAAC/python.sh`.
- **Cosmos3-Nano**: NVIDIA's vision-language model. It looks at the camera image and reports cubes and their colours (stage 2). It runs in a separate Python environment, `$COSMOS`.
- **Host Python**: plain Python for planning and video encoding (stages 3 and 5): `fanuc_er4ia_sim/.venv`.
- **venv**: an isolated folder of Python packages, so the three environments can't break each other.
- **Weights**: the model's trained numbers (35 GB of files). They're downloaded, never committed.
- **Driver**: the system software that lets programs use the GPU. Isaac Sim 6.0 is picky about its version.
- **EULA**: the license agreement you must accept before Isaac Sim runs. Read it yourself; the script won't accept it for you.
- **Seed**: a number that picks one random cube layout. The same seed always gives the same layout.

## Cost rules

- Brev bills **every hour the instance is running**, whether or not you use it. **Stop it when you step away.** A stopped instance keeps its disk (for a small storage fee) and frees the GPU.
- A 1× L40S instance cost about $2.69/h plus $0.04/h storage in a [July 2026 forum report](https://forums.developer.nvidia.com/t/brev-gpu-recommendation-for-a-digital-twin-internship-project-modular-production-line/372324). Check the current price when you create it.
- Expected spend for this runbook: about 1 h of setup (mostly downloading about 50 GB), then the first run, then the dev sweep. Record real times in the table at the end, so later estimates use real numbers.

## 1. Get a machine

**Brev:** create an instance with **1× NVIDIA L40S**, Linux, with Stop/Start enabled and **at least 150 GB of disk**. The L40S is the GPU [NVIDIA's own Brev guide for Isaac Sim](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/installation/install_advanced_cloud_setup_brev.html) selects. Use the team Brev credits; don't attach a personal card.

- If you use NVIDIA's **Isaac launchable** instead of a plain instance, check its Isaac Sim version first (see step 3). Current NVIDIA docs already mention 6.1, and the starter needs **6.0**.

**DGX Spark:** run `nvidia-smi` first. The driver must be **580.x**. If it shows 595 or newer, update it through the DGX Spark Dashboard; [details here](arm-findings.md).

## 2. Get the code

```bash
git clone https://github.com/ALL-Applied-AI-Network/msoe-ai-club-rockwell-automation-nvidia-hackath-gunnar-seversen-s-team-05192cd956.git team
cd team
```

## 3. Run the setup script

Read the Isaac Sim license first. It's linked from the [Isaac Sim pip install page](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/install_python.html), and Isaac also prints it on first use. If you agree:

```bash
export OMNI_KIT_ACCEPT_EULA=YES
```

The Cosmos3-Nano weights are **not gated**, so no Hugging Face token is required. A token avoids download rate limits. If you use one, put it only in the environment, never in a file in this repo:

```bash
export HF_TOKEN=hf_your_token_here
```

Then run the script:

```bash
scripts/gpu_setup.sh
```

Everything goes under `~/fanuc-gpu/` (change it with `WORK=...`). The script is safe to rerun: after fixing a problem, run it again and it skips the finished steps.

What each step does, and why:

| Step | What it does | Why |
|---|---|---|
| 1. Machine check | Prints the CPU architecture, GPU and driver. Warns if the driver isn't 580.x. Requires 100 GB of free disk. Installs `uv` if it's missing. | Catches the known driver crash and a full disk before a long download. `uv` provides Python 3.12, which Isaac Sim requires. |
| 2. Isaac Sim 6.0 | Uses an existing install if `$ISAAC/python.sh` exists. Otherwise pip-installs `isaacsim[all,extscache]==6.0.0.1` with `torch==2.11.0` into `~/fanuc-gpu/isaacsim/venv`, and writes a small `python.sh` that forwards to it. **Stops if the version isn't 6.0.** | The ER-4iA robot model only ships with Isaac Sim 6.0. The starter always calls `$ISAAC/python.sh`, which only a standalone install has, hence the stand-in file. |
| 3. Cosmos environment | Creates `~/fanuc-gpu/cosmos-venv` with torch 2.11.0 and torchvision 0.26.0 (CUDA 13), `transformers==5.9.0`, `accelerate`, `huggingface_hub`, `transformers-cosmos3` at a pinned commit, and `requirements-cosmos.txt`. | `perceive.py` imports `transformers_cosmos3.Cosmos3ForConditionalGeneration`. That package is NVIDIA's plugin in the public [cosmos-framework repo](https://github.com/nvidia/cosmos-framework/tree/main/packages/transformers-cosmos3) (`packages/transformers-cosmos3`). 5.9.0 is the `transformers` version that plugin's lock file was tested with. |
| 4. Weights | Downloads `nvidia/Cosmos3-Nano` at a pinned revision into `~/fanuc-gpu/models/Cosmos3-Nano`, about 35 GB, skipping example media. | Perception can't run without them. Pinning means every run uses the same model. |
| 5. Host environment | Runs the starter's `bootstrap.sh`: host packages, textures, **34 host tests**. | Proves planning code and textures are ready on this machine. |
| 6. Environment file | Writes `~/fanuc-gpu/env.sh` with `ISAAC`, `COSMOS` and `COSMOS3_NANO_PATH`. | One `source` line sets everything in each new terminal. |
| 7. Dependency checks | The two checks from `SETUP.md` (CUDA visible to torch; Cosmos3-Nano loads), then builds the scene headless into `runs/scene.usd`. | Proves each environment works on its own before a full run, so a failure points at one component. |

At the end it writes `~/fanuc-gpu/setup_record.txt`, recording versions, GPU and driver. It also writes `freeze-*.txt`, the exact package lists. Copy these into the results table below.

## 4. First run (reference seed)

```bash
source ~/fanuc-gpu/env.sh
fanuc_er4ia_sim/.venv/bin/python harness/run_sweep.py run sweeps/first \
    --seeds 20261009 --render --usd-per-hour 2.69
```

This runs the same five stages as `fanuc_er4ia_sim/run_sort_pipeline.sh`, on the reference layout the starter was validated on, timing each stage. `--render` also writes the review videos. `--usd-per-hour` adds a cost line; use the real price.

**Pass:** `sweeps/first/summary.md` shows `success`, and `sweeps/first/seed_20261009/execution_report.json` has `task_complete: true`, `verified_pickups: 6` and `verified_placements: 6`. Watch `sort_table.mp4` once.

**If it fails:** `summary.md` names the first failing stage, and `seed_20261009/logs/<stage>.log` holds that stage's output. [pipeline.md](pipeline.md) under "Failure signatures" explains each outcome. Per the starter's rules, diagnose the failure; don't loosen thresholds.

## 5. Dev sweep

```bash
fanuc_er4ia_sim/.venv/bin/python harness/run_sweep.py run sweeps/dev --set dev --usd-per-hour 2.69
```

This runs the 30 dev seeds in `harness/seeds.json` with physics only (no frame rendering, which is cheaper). It's safe to interrupt: rerunning the same command skips finished seeds. `sweeps/dev/summary.md` and `summary.csv` are the baseline numbers.

Run the **held-out** set (`--set heldout`) only at project milestones, never while tuning.

Copy `summary.md` and `summary.csv` into `docs/results/` before stopping the instance. The `sweeps/` folder is git-ignored.

## 6. Stop the machine

On Brev, **Stop** the instance. Commit and push anything you want to keep first.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Isaac crashes with a segmentation fault during "RTX" startup | Driver isn't R580 | Install a 580.x driver (on Spark, through the Dashboard) |
| Step 2 says "found 6.1..." or "unknown" | The launchable or container has another Isaac Sim version | `unset ISAAC` and rerun; the script installs 6.0 with pip |
| `Cosmos3-Nano not found` | `COSMOS3_NANO_PATH` not set | `source ~/fanuc-gpu/env.sh` |
| `CUDA: False` in step 7 | torch built for the wrong CUDA, or no GPU visible | Check `nvidia-smi`. Try `TORCH_INDEX=https://download.pytorch.org/whl/cu128` if the driver is older than CUDA 13 supports |
| Scene build wrote no `scene.usd` | Robot asset couldn't be downloaded | Check the network; see `FANUC_ROBOT_USD` in `fanuc_er4ia_sim/SETUP.md` |
| A module fails to import on Spark | `libgomp` preload | The setup's `python.sh` sets `LD_PRELOAD`; with a standalone install, add it as the Isaac docs describe |
| Disk full during download | Under 100 GB free | Make the disk bigger, or set `WORK` to a larger volume |

## Known speed-up for later

`perceive.py` loads the 35 GB model again for every seed. For large sweeps, a perception process that loads the model once and serves many seeds would save that load time on every run. We haven't made this change; it would be our own modification, measured against the baseline.

## Results record

Fill in one row per machine after the first run:

| Date | Machine | GPU | Driver | Isaac | Setup time | First run (s) | Result | $/h | Notes |
|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | |
