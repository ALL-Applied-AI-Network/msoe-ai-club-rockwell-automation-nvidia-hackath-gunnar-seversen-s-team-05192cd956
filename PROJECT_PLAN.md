# Project plan: Vision-Guided Pick and Sort for Fast Changeovers on the FANUC ER-4iA

Dataset 3 (Grasping and Sorting). This document expands on our team plan submission ([TEAM_PLAN.md](TEAM_PLAN.md)). It will change as we learn more.

## Summary

We are starting from the supplied FANUC ER-4iA starter, which stacks six cubes in Isaac Sim using camera perception (Cosmos3-Nano plus image geometry) instead of fixed taught positions. We will:

1. measure how reliable it really is across many randomized layouts;
2. fix the most common failures and add grasp checking with retry;
3. run it on the physical arm under supervision and report how simulation and reality differ.

As a stretch goal, we will design fingers that can grasp the line's vials and caps.

## Problem

Robot arms on most lines replay taught motions. That only works when every part arrives in the same place, so plants either fixture each part or re-teach the robot whenever the product changes. On a high-mix, low-volume line like CSI's, changeovers are frequent, and each one costs setup time and needs a skilled person.

A cell that finds parts with its cameras and adapts its grasp avoids most of that. Plants will only trust it, though, if its reliability is measured, its failures are understood, and it recovers from a bad grasp instead of carrying on blindly.

## Starting point

What the starter provides:
- A five-stage pipeline:
  1. capture (Isaac Sim, 4K table camera)
  2. perception (Cosmos3-Nano finds and classifies each cube; calibrated image geometry measures position and rotation)
  3. grasp and stack planning
  4. physics-based execution in Isaac Sim
  5. JSON and video reports
- A calibrated twin of the cell: the arm, an SMC MHZL2-16D2 gripper model and three cameras (table, side, wrist).
- Seeded random cube layouts (`scene_config.hackathon_cubes(seed)`).
- 33 tests that run without a GPU. They pass on our machines.

What it does not provide, and where our work goes:
- **No interface to the physical controller.** Execution drives only the simulated arm.
- **Validated on one layout only**, and only in simulation.
- **Cubes only**, assumed upright, of known size, on a calibrated flat surface.
- **The fingers open to 12 mm at most**, so they cannot grasp the 27 mm vials or 31.75 mm caps.
- **Calibration not fully checked:**
  - lens distortion is not modeled;
  - finger friction has not been measured;
  - the table and wrist cameras were not re-checked against the real cell after the model was rebuilt.

## Approach and milestones

| Phase | Dates | Work | Done when |
|---|---|---|---|
| 0. Setup | Oct 13–18 | Run host setup and tests. Get Isaac Sim 6.0 and Cosmos3-Nano running on a GPU. Do one full end-to-end run. | `execution_report.json` shows `task_complete: true`, 6 pickups and 6 placements, on our own run |
| 1. Baseline | Oct 15–20 | Run the unmodified starter on a fixed set of 30–50 seeds. Record the outcome of each one and which stage failed. | Baseline success rate and a failure catalog ranked by frequency |
| 2. Robustness | Oct 19–28 | Fix failure causes in order of frequency. Add variation one factor at a time: rotation, then layout density, then distractors, then lighting. Add a wrist-camera check after each grasp, with retry. | Each change measured on the same seeds, and held-out results reported |
| 3. Physical transfer | Oct 21–30 | Agree with mentors how planned motions reach the arm. Write the motion export. Run supervised physical trials and log every attempt. | Physical success rate, and differences from simulation explained |
| 4. Stretch | Oct 15–30, in parallel | Design fingers for vials and caps, get them printed and reviewed, then extend the sort to those parts. | Reviewed fingers, and a sim (and if possible physical) success rate on vials and caps |
| Submission | Oct 31–Nov 1 | Final numbers, video, one-page summary, README. | Submitted by Nov 1, 11:59 PM CT |

## How we will measure

- **Two fixed sets of seeds:**
  - a development set we use while fixing problems;
  - a held-out set we only run at milestones, so we can't tune ourselves into a good-looking number.
- **Per-run metrics:**
  - task success (all six cubes stacked);
  - pickups and placements verified;
  - placement position and rotation error;
  - cycle time;
  - retries used.
- **Failure attribution:** every failed run is tagged with the first stage that went wrong: perception, planning, grasp or placement.
- **No ground truth in the control loop.** Simulator object poses are used only to score results, never to guide grasps. The starter's confidence and safety checks are not loosened to make runs pass.
- **Physical trials:** every attempt is logged, including:
  - software version;
  - starting layout;
  - prediction and result;
  - any operator intervention.

  We report simulation and physical results side by side.

## Physical testing and safety

- We will not command the arm, change controller settings or connect anything to the plant network without the plant manager and an assigned mentor.
- Printed fingers go on the arm only after CSI review.
- Before requesting a test slot, we will:
  - freeze the version to be tested;
  - write a start/stop procedure;
  - list the metrics to record;
  - test failure handling on saved data.
- **Joint 3 convention:** the controller and the simulator define joint 3 differently (`sim_q3 = controller_J3 + J2`). We will apply this conversion only in the export step, and check it with mentors before any motion runs.

## Team and roles

| Member | Role |
|---|---|
| Gunnar Seversen (CS) | Simulation pipeline, test harness and metrics, robustness work, motion export code |
| Josh Cygan (EE, production-line internship) | Physical cell integration, test plan and safety, calibration checks, finger design, business case |
| [Other teammates] | Scene variation, Cosmos experiments, video and summary |

## Resources requested

- **Compute:**
  - DGX Spark at UWM as the main machine for layout sweeps;
  - Brev L40S, about 30 hours ($100), for setup and overflow;
  - build.nvidia.com for Cosmos prompt tests.
- **AI tools:** one $100/month Claude plan (lead developer) and one $20/month Claude plan (physical integration).
- **Mentors:**
  - NVIDIA: Isaac Sim and Cosmos.
  - Rockwell Automation: robot-cell practice and the business case.
  - CSI: the physical cell, finger printing and review, test scheduling.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| No defined way to send motions to the physical arm | Asked the organizers first. Design the motion export to fit whichever method they choose (ROS 2 driver or a mentor-run controller program). |
| Few physical test slots | Request early. Get the most from each slot with a prepared, frozen test plan. |
| Starter not validated on the ARM-based DGX Spark | Brev L40S as a fallback. Update the compute estimate after the first run. |
| Sim and reality differ (lighting, friction, calibration) | Compare real camera samples with renders early. Report the gap honestly. |
| Finger print and review takes too long | Start the design in week 1. Treat vials and caps as a stretch goal, not the core result. |

## Open questions for organizers

1. Is the `fanuc_er4ia_sim` cube-stacking starter (calibration from v0.5, Oct 9) the current official twin?
2. How do planned motions reach the physical arm during a supervised test?
3. Which gripper is installed: SMC MHZL2-16D2 or SCHUNK?
4. What is the turnaround for printing and reviewing fingers?
5. How many physical test slots can each team get, and when?
6. Where do we get Cosmos3-Nano weights, and is the Brev launchable on Isaac Sim 6.0?

## Out of scope

- Arbitrary 3D pose estimation (6-DoF): the starter assumes upright parts on a flat surface, and so will we.
- Any change to the cell's PLC, safety system or production programs.
- Training on real line data. Training and tuning come from the twin; real data is used for validation.
