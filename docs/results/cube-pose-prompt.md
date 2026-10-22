# Cube pose prompt: removing the example yaw (Oct 21, 2026)

Run on Brev (1× NVIDIA L40S, driver 580.178.04, Isaac Sim 6.0.0.1, Cosmos3-Nano revision e59a53c) with `harness/run_sweep.py`, physics only (no frame rendering).

## Question

In the first baseline sweep, every failure stopped at the perception gate. Most failures had one cube rejected with `cube_pose_missing_or_invalid`, even though the image geometry fit for that cube was good (silhouette IoU about 0.96). Why, and does fixing it raise the success rate without loosening any gate?

## What was wrong

For each cube, `perceive.py` measures yaw from the image, then asks Cosmos to confirm the cube and report that measured yaw. The pose is accepted only if Cosmos's yaw is within 3° of the measurement (`perceive.py`, `inspect_cube_poses`).

The prompt's example answer contained a concrete value, `"yaw_deg":14.2`. For the blue cube measured at about −35°, Cosmos often returned that example character for character (even its no-space formatting) instead of the measured value. The 3° check correctly rejected it, and the all-six inventory gate then cancelled the whole run.

The same layout could pass in one run and fail in the next. Render noise changes the capture slightly, and that is enough to flip Cosmos's answer.

## Change

Commit 5e706f6 on `fix-cube-pose-prompt`, compared against the starter baseline at b863603:

```diff
-Return only JSON: {"category":"cube","colour":"blue","yaw_deg":14.2,
+Return only JSON: {"category":"cube","colour":"blue","yaw_deg":<measured yaw_deg>,
 "pose_confidence":0.9,"reason":"visible cube geometry and colour"}.
-Use the measured yaw value from this query, not the example value above."""
+Replace <measured yaw_deg> with the yaw_deg number measured for THIS cube below."""
```

All gates are unchanged:
- pose confidence of at least 0.8;
- Cosmos yaw within 3° of the measurement;
- silhouette IoU of at least 0.85;
- all six cubes must pass.

A host test (`test_cube_pose_prompt_has_no_example_yaw_to_copy`) fails if the prompt contains a numeric example yaw again.

## Method

- The 30 dev seeds from `harness/seeds.json`, run **3 times per commit**, because a single run per seed isn't repeatable.
- Baseline run 1 is the first dev sweep (Oct 21, 01:56 UTC). Runs 2 and 3 and all fix runs followed on the same instance (Oct 21, 20:13–23:15 UTC).
- Each failed run is assigned one cause, from its `sort_plan.json` and the raw Cosmos replies in `cube_pose_crops/`, ignoring the `incomplete_cube_colour_set` skips that follow from another cube's rejection:

| Cause | How it's identified |
|---|---|
| Copied example yaw | A rejected cube's Cosmos reply has `"yaw_deg":14.2`, while its measured yaw is not 14.2 |
| Wrong yaw | A rejected cube's Cosmos reply has some other yaw more than 3° from the measurement |
| Box off target | A rejected cube was never sent to Cosmos, because its silhouette IoU was below 0.85 (in practice 0.0: no cube where Cosmos's box was) |
| Missed cubes | No cube was rejected; Cosmos found fewer than two cubes of some colour |
| Outside work surface | The only primary rejection was `outside_work_surface` |

Ground truth was used only to score runs.

## Results

| | Run 1 | Run 2 | Run 3 | **Total** |
|---|---|---|---|---|
| Baseline (b863603) | 13/30 | 9/30 | 16/30 | **38/90 (42%)** |
| Fix (5e706f6) | 20/30 | 21/30 | 22/30 | **63/90 (70%)** |

| Seeds that succeeded | 3 of 3 runs | 2 of 3 | 1 of 3 | 0 of 3 |
|---|---|---|---|---|
| Baseline | 4 | 8 | 10 | 8 |
| Fix | **14** | 9 | 3 | **4** |

### Failure catalog

| Cause | Baseline | Fix |
|---|---|---|
| Copied example yaw (14.2) | **38** | **0** |
| Wrong yaw | 0 | 11 |
| Box off target | 3 | 7 |
| Missed cubes | 7 | 6 |
| Outside work surface | 4 | 3 |
| **Total failures** | **52** | **27** |

- In the fix runs, one Cosmos reply did say 14.2, but that cube was measured at 14.196°, so it was correct.
- Per-seed outcomes for all 180 runs: [per_seed_outcomes.csv](cube-pose-prompt/per_seed_outcomes.csv).
- Median time per successful fix run: 80.8 s. The six sweeps used 3.6 GPU-hours, about $6.25 at $1.74/h.

## What this means

- **The copying failure is gone,** and success rose from 42% to 70% with no gate loosened.
- **The next yaw failure is negative angles.** All 11 "wrong yaw" replies came for cubes with a negative measured yaw. Cosmos either dropped the sign (measured −2.00°, replied 2.00) or converted to 0–360° incorrectly (measured −1.86°, replied 348.14; measured −22.92°, replied 297.08). Seed 28 fails this way in all 3 fix runs. Because cube yaw repeats every 90°, sending the measurement already folded into [0°, 90°) would remove both mistakes, and the 3° check already compares angles modulo 90°.
- **The remaining 16 failures are detection errors:** cubes missed, a "cube" box placed on empty table (often next to a yellow cap), or a detection outside the work surface. Seed 1 now fails this way in all 3 fix runs. These need changes to the detection step itself, which is a bigger change.
- **Run-to-run variation is large** (the baseline ranged from 9/30 to 16/30), so single sweeps can't measure a change reliably. Future comparisons should keep 3 or more runs per commit.

## Not checked here

- The held-out seeds. They're reserved for milestones.
- Rendered runs and the side-camera video for the fix.
- Wider cube rotations, other lighting, or more distractors.
- Real camera images or the physical arm. This change affects only the prompt text, so it doesn't change any arm motion.
- The cause labels come from a one-off analysis of the run folders, not from `harness/run_sweep.py`, whose summary reports these failures only as `perception`.
