# Team plan submission (Oct 14, 2026)

The text we submitted in the ALL AI Network team plan form, field by field. The fuller plan is in [PROJECT_PLAN.md](PROJECT_PLAN.md).

---

## Project title

Vision-Guided Pick and Sort for Fast Changeovers on the FANUC ER-4iA

---

## Problem and initial approach

Problem: Industrial arms are usually taught fixed motions. When parts arrive in different positions or orientations, or the product changes, the robot has to be re-taught or the parts have to be fixtured. On a high-mix, low-volume line that costs setup time at every changeover. We want the ER-4iA cell to pick and sort parts from wherever they land, using its cameras, and to prove how reliably it does that.

Initial approach:
1. Baseline: run the supplied FANUC starter (Isaac Sim capture → Cosmos3-Nano + image-geometry pose → grasp planning → simulated execution) unchanged across many randomized cube layouts. Record pick success, placement error, cycle time and the cause of every failure.
2. Robustness: fix the most common failure causes, then widen the variation one factor at a time (rotation, layout, distractors, lighting). Add a wrist-camera check after each grasp so a missed pick is detected and retried. Every change is measured against the same fixed set of test layouts.
3. Physical transfer: with mentors, turn the planned motions into something that can run on the real arm, compare a small set of supervised physical trials with simulation, and report where they disagree.
4. Stretch: design and print fingers that can grasp the line's actual vials and caps (the current fingers open to 12 mm; vials are 27 mm), and extend the sort to those parts.

Deliverable: measured success rates against the starter baseline, in simulation and on the physical arm, plus a business case for vision-guided picking versus re-teaching and fixturing at changeovers.

---

## Dataset

Dataset 3: Grasping and Sorting (already selected)

---

## Additional data needed and why

- Real camera samples from the table, side and wrist cameras of the physical cell, so we can check how closely the twin's renders match reality before relying on them.
- The camera calibration files (ArUco solves, intrinsics and lens distortion). The twin uses pinhole approximations without distortion.
- Finger CAD (STEP) and confirmation of the installed gripper. The starter models an SMC MHZL2-16D2; the event page lists a SCHUNK gripper.
- A list of the physical objects available for picking, with dimensions, so we can tell which ones the current fingers can grasp.
- A few recorded physical pick attempts, successful or not, to compare against simulated grasps.

---

## Compute requested (checkboxes)

- [x] Brev
- [ ] Dell GB10 at MSOE (Rosie)
- [x] DGX Spark at UWM
- [ ] CSI Emulate3D workstation
- [x] build.nvidia.com only
- [ ] No additional compute

---

## Compute estimate and justification

- DGX Spark: the baseline sweep of randomized layouts and most iteration runs, once access opens. We are UWM students, so we can also use it in person.
- Brev L40S (Isaac Sim launchable, AWS, Start/Stop), about $3/hr: environment setup and the first end-to-end run while DGX Spark access is pending, plus overflow when the shared Sparks are busy. About 30 hrs, or about $90. We request $100 in Brev credits.

---

## AI agent tools or credits requested (Claude / Codex plans)

- One $100/month Claude plan for Gunnar Seversen. The starter is about 6,600 lines of Python spread across Isaac Sim, Cosmos and host interpreters, and most work happens in long agent sessions.
- One $20/month Claude plan for Josh Cygan, for the physical-integration work: motion export for the real arm, calibration checks and finger-design scripts.

---

## Mentor support requested (checkboxes)

- [x] NVIDIA
- [x] Rockwell Automation
- [x] Emulate3D / CSI

---

## Questions for the organizers

Is the `fanuc_er4ia_sim` cube-stacking starter (calibration imported from v0.5, Oct 9) the current official twin, or will a newer version be released?

During a supervised physical test, how do our planned motions reach the arm: the FANUC ROS 2 driver, a mentor-run controller program from exported waypoints, or something else?

Which gripper is installed on the physical arm: the SMC MHZL2-16D2 (as modeled) or a SCHUNK?

What is the turnaround for printing and safety review of custom fingers?

How many physical test slots can each team get, and when do they open?

Where do we get Cosmos3-Nano weights, and is Isaac Sim 6.0 the version in the Brev launchable?
