# Host-only feasibility sweep (Oct 15, 2026)

Run on a Mac, with no GPU, using `harness/feasibility_sweep.py` at the starter baseline plus the seed hook.

## Question

Before any GPU time is spent: are there layout seeds that the starter **cannot** complete for reasons unrelated to perception or physics? Specifically:

- a cube outside the camera's view;
- a plan the starter's own checks reject;
- an arm motion the IK can't follow.

## Method

For each seed:

1. Build the layout with `scene_config.hackathon_cubes(seed)`. The cube yaws are the starter's fixed `SORT_CUBE_YAWS_DEG`, optionally rotated by an extra offset.
2. Check that every cube's top corners project inside the 3840×2160 table-camera image, using the synthetic calibrated camera from `test_support.py`.
3. Give the real planner (`plan_sort.build_plan`) *ideal* detections of that layout, and run the executor's own `sort_scene.validate_plan`.
4. Replay `sort_scene.py`'s motion loop without Isaac. That means all 11 segments per cube, one `ik.solve` call per 1/30 s frame, the same retry, and the same refusal rules (fingertip more than 1 mm off target, or jaw direction misaligned).

`sort_scene.py` seeds every IK call from the previously *commanded* joints, never from physics. So for the same plan, this replay hits exactly the IK failures the simulator would.

This is offline analysis only. The ideal detections come from configured layout poses, and nothing here feeds the pipeline.

## Results

| Sweep | Checks | Feasible | IK retries | Worst fingertip error | Smallest joint-limit margin | Smallest image margin |
|---|---|---|---|---|---|---|
| Seeds 0–999 + 20261009, yaw offset 0° and ±3° | 3,003 | **3,003** | 0 | 0.1 mm (limit 1 mm) | 26.4° (J3, seed 300) | 464 px (seed 30) |
| Seeds 0–199, every cube rotated an extra ±20° and ±40° | 800 | **800** | 0 | 0.1 mm | 26.6° (J3, seed 21) | 463 px (seed 30) |

- The ±3° offset is the largest yaw disagreement the perception gate accepts, so no seed is fragile to small yaw errors.
- The tightest joint is almost always J3 (the elbow). It's J5 in about 2% of checks. Both stay at least 26° from their limits.
- **All 30 dev seeds and all 20 held-out seeds** (`harness/seeds.json`) are feasible.
- Per-seed data: [seeds_0-999_yaw0_pm3.csv](feasibility/seeds_0-999_yaw0_pm3.csv) and [seeds_0-199_yaw_pm20_pm40.csv](feasibility/seeds_0-199_yaw_pm20_pm40.csv).

## What this means

- **No seed has to be dropped.** The layout generator samples a conservative area (x 0.24–0.46 m, y −0.15–0.28 m) that is comfortably reachable and visible. So **any baseline failure on the GPU will come from perception or physics** (grasp, slip, placement, stack support), not from reachability or planning geometry. That narrows where the starter can fail, and therefore where our improvements should go.
- **Wider cube rotations are kinematically safe.** Any rotation, folded into the square cube's ±45° symmetry range, is fine. The rotation step of our robustness phase only needs to test perception and grasping.
- Widening the layout area later (for example, toward the table edges) is where reachability could start to matter. Rerun this sweep with the new sampler first; it's free.

## Not checked here

- Physics: whether the fingers actually hold the cube, whether it slips, or whether the stack stays up.
- Collisions between the gripper and neighbouring cubes, caps or vials. The generator keeps cubes at least 65 mm apart and 55 mm from vials, which is much more than the 12 mm gripper opening.
- Real perception error, beyond the uniform ±3° yaw offset.
- Each check took about 0.73 s on an Apple-silicon Mac.
