# Negative yaw: showing the measured angle in [0°, 90°) (Oct 22, 2026)

Run on Brev (1× NVIDIA L40S, driver 580.178.04, Isaac Sim 6.0.0.1, Cosmos3-Nano revision e59a53c) with `harness/run_sweep.py`, physics only, plus one rendered run.

## Question

After [the prompt fix](cube-pose-prompt.md), 11 of the remaining 27 dev-sweep failures were Cosmos returning a wrong yaw. Every one of those cubes had a **negative** measured yaw. Does sending the yaw as a positive number remove them, without loosening any gate?

## What was wrong

Cosmos is asked to repeat the yaw that image geometry measured, and the pose is accepted only if its reply is within 3° of the measurement. For negative measurements, Cosmos either:

- dropped the sign: measured −2.00°, replied 2.00;
- or converted to 0–360° incorrectly: measured −1.86°, replied 348.14 (correct would be 358.14), and measured −22.92°, replied 297.08.

## Change

Commit 2fcca72 on `fix-negative-yaw`, compared against 5e706f6 (fix 1, now on `main`):

```diff
-            yaw_deg=round(yaw, 4),
+            yaw_deg=round(yaw % 90, 4),
```

A square cube looks the same every 90°, so −2° and 88° are the same pose. Two things make this safe:
- the 3° check already compares angles modulo 90° (`square_yaw` in `cube_pose.py`);
- the accepted pose is folded back to −45°…45° before planning.

So **the grasp angle sent to the planner is unchanged**. The measured value isn't used anywhere else. All gates are unchanged. A host test (`test_negative_yaw_is_shown_to_cosmos_in_square_range`) checks that a −2° cube is shown as 88°, that an 88° reply is accepted, and that the planner still gets −2°. It fails on the old code.

## Method

- The 30 dev seeds, **3 runs per commit**. The fix 1 runs (Oct 21, 21:23–23:15 UTC) are the "before"; the fix 2 runs (Oct 22, 02:45–04:45 UTC) are the "after", on the same instance.
- Causes are assigned as in [cube-pose-prompt.md](cube-pose-prompt.md#method), from `sort_plan.json` and the raw Cosmos replies.

## Results

| | Run 1 | Run 2 | Run 3 | **Total** |
|---|---|---|---|---|
| Fix 1 (5e706f6) | 20/30 | 21/30 | 22/30 | **63/90 (70%)** |
| Fix 2 (2fcca72) | 22/30 | 21/30 | 23/30 | **66/90 (73%)** |

| Seeds that succeeded | 3 of 3 runs | 2 of 3 | 1 of 3 | 0 of 3 |
|---|---|---|---|---|
| Fix 1 | 14 | 9 | 3 | 4 |
| Fix 2 | **18** | 3 | 6 | **3** |

### Failure catalog

| Cause | Fix 1 | Fix 2 |
|---|---|---|
| Wrong yaw | 11 | **0** |
| Outside work surface | 3 | 11 |
| Missed cubes | 6 | 7 |
| Box off target | 7 | 6 |
| **Total failures** | **27** | **24** |

- The rendered run of seed 20261009 succeeded: `task_complete: true`, 6 verified pickups, 6 verified placements.
- Per-seed outcomes for all 180 runs: [per_seed_outcomes.csv](negative-yaw/per_seed_outcomes.csv).
- Median time per successful run: 80.0 s. The three sweeps plus the rendered run used 2.0 GPU-hours, about $3.50 at $1.74/h.

## What this means

- **The wrong-yaw failure is gone**, and 18 seeds now pass all three runs (was 14). Fewer seeds pass exactly 2 of 3 (3 vs 9): run-to-run variation is still large.
- **The overall gain (+3 runs) is small** because detection failures were higher in these runs (24 vs 16). This isn't caused by the change. Detection runs before the pose step in `perceive.py` (the initial query, then `audit_stack_colours`, then `inspect_cube_poses`), so changing what the pose step shows Cosmos can't affect which cubes are detected. Detection results vary from run to run with render noise, as the baseline showed (9 to 16 of 30).
- **Every remaining failure is a detection failure.** That's the next thing to fix.

## Detection findings

**Off-surface detections are mostly the parked gripper.** Across all six fix runs there were 183 detections outside the work surface, and the work-surface gate rejected every one:

| Where Cosmos put the "cube" | Detections |
|---|---|
| The parked gripper, at three fixed points in the top-left of the image (its orange block, a yellow-tinted housing edge, the wrist top): reported as yellow cubes | 169 |
| The gripper's blue fitting: reported as blue cubes | 4 |
| Mixed-unit replies (one coordinate as a fraction, the other on a 0–1000 grid, e.g. `[0.56, 732]`), read as a point at the image's left edge | 10 |

- The gripper never moves between layouts before capture, so the same three points repeat.
- These false detections only fail a run when Cosmos **also** misses the real cube of that colour, which happened in 11 fix 2 runs.
- We checked whether they come from copying the prompt's example coordinates (`[0.4, 0.5]`) and found no copies.

**Likely next change:** crop the image to the work surface before asking Cosmos to find cubes. The work surface is already defined by the camera calibration the planner uses, so no ground truth is involved. The crop would:
- remove the gripper from view;
- make each 10 mm cube several times larger in the image, which may help with the missed cubes and off-target boxes.

## Not checked here

- The held-out seeds.
- A fresh baseline or fix 1 run in the same session as fix 2, which would make the detection comparison fairer.
- Real camera images or the physical arm. This change affects only the number shown to Cosmos, not the planned motion.
- Whether the mixed-unit replies also occur in the initial detection query, rather than only in the colour audit.
