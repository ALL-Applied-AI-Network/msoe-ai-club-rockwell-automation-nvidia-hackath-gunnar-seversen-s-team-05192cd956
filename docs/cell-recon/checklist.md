# CSI cell scouting checklist (look-only visit)

For Gunnar and Josh, to fill in at the FANUC ER-4iA cell. Each item lists what the **digital twin currently assumes** (from `fanuc_er4ia_sim/scene_config.py` and its docs), so a mismatch shows up while you're still in the room. Every mismatch we find is a sim-to-real gap to report.

Date: ______  Who: ______  CSI staff present: ______

## Ground rules

- [ ] **Look only.** Don't power, jog or command the arm. Don't touch the teach pendant, controller, cables or network. Building access doesn't include robot access; that needs the plant manager or a mentor.
- [ ] Ask staff before taking photos. **No people in frame**, and nothing the plant marks as confidential.
- [ ] Measure only parts that are loose or safely reachable with the arm stopped. If a measurement needs the arm moved, write it down as a question for a mentor instead.
- [ ] Bring: calipers, a steel ruler or tape measure, a phone, a plain white sheet of paper (as a colour and white reference), and this list.

## Where things go

- Photos go in `docs/cell-recon/photos/`, named `YYYYMMDD_<topic>_<n>.jpg` (for example `20261020_gripper_label_1.jpg`). Resize to at most 2 MB each before committing.
- **No videos in git** (`*.mp4` and `*.mov` are ignored). Keep them in the team drive and link them here.
- Fill in measurements directly in this file and commit it.

## 1. Gripper

| Item | Twin assumes | Observed |
|---|---|---|
| Actuator model (label photo) | SMC MHZL2-16D2 (the event page says SCHUNK) | |
| Drive type (air lines? electric cable?) | Pneumatic parallel gripper | |
| Stroke per jaw | 6 mm | |

- [ ] Photo of the actuator label, readable
- [ ] Photo of the whole tool from the side, with a ruler in frame

## 2. Fingers and gap

Measure with calipers, with the gripper stopped and only if staff allow it.

| Item | Twin assumes | Observed |
|---|---|---|
| Straight-face gap, open | 12 mm | |
| Straight-face gap, closed | 0 mm | |
| Fingertip (hook) gap, open | 15 ± 2 mm (model 15.99) | |
| Fingertip (hook) gap, closed | 4 ± 1 mm (model 3.99) | |
| Exposed finger length | 76 mm | |
| Finger width × thickness | 12 × 6 mm | |
| Fingertip material or tape (friction) | High-friction tip over the distal 32 mm, unmeasured | |
| Faceplate to fingertip length | 223 mm (controller UTOOL1) | ask a mentor |

- [ ] Close-up of both fingertips, from the front and the side
- [ ] Is anything covering the tips (tape, rubber)? Photo of it

## 3. Cameras

The twin has three cameras. Positions are in metres in the robot base frame: +X away from the robot toward the work area, +Y to the robot's left, Z measured from the base mounting face.

| Camera | Twin assumes | Observed (mount, model, cable, rough position) |
|---|---|---|
| Table | About 0.80 m above the base plane, at x ≈ 0.78, y ≈ −0.04, looking down and back toward the robot. 1920×1080, about 11.2 mm focal length | |
| Side | At x ≈ 0.46, y ≈ +0.63, about 0.14 m above the base plane, looking across the table in −Y | |
| Wrist | On the J6 link, about 98 mm to the side of the tool axis, looking along the tool. 1280×720 | |

- [ ] Camera make/model labels (photo of each)
- [ ] Connection type for each (USB / GigE / other) and where the cable goes (which PC)
- [ ] Photo of each mount, showing how it attaches
- [ ] Rough tape-measure position of the table camera relative to the robot base

## 4. ArUco markers

ArUco markers are printed black-and-white squares that software can find to work out where a camera is. The twin's camera positions came from "ArUco solves" we haven't been given.

- [ ] Are markers present? Where? (photo of each, ruler in frame)
- [ ] Marker edge length: ______ mm   Marker IDs or dictionary, if printed: ______
- [ ] Are they fixed in place, or were they only used once for calibration?

## 5. Objects on and near the table

| Object | Twin assumes | Count seen | Measured size | Colour(s) |
|---|---|---|---|---|
| Cubes | 10 mm edge, 4 g; yellow, blue, red (the original real scene had 2 yellow) | | | |
| Vials or tubes | Sim: 17 mm diameter × 140 mm (render-fit). USD comment: 27.18 mm × 203 mm | | | |
| Caps | 31.75 mm diameter × 15.7 mm tall | | | |
| Anything else loose | — | | | |

- [ ] Photo of each object type next to a ruler
- [ ] Which objects can the current fingers grasp? (anything wider than about 12 mm can't be grasped)

## 6. Work surface

| Item | Twin assumes | Observed |
|---|---|---|
| Surface relative to the robot base face | 5.1 mm below | |
| Covering | Flat white paper backdrop, from about x 0.18 to 0.71 m, 0.94 m wide; a 2 mm mat | |
| Table extent from the robot base | x −0.37 to 0.76 m, y −0.77 to 0.79 m | |
| Fixtures or obstacles in reach | None used in the cube task | |

- [ ] Overhead photo of the whole table, if possible from near the table camera

## 7. Controller, PC and network

Record what's labelled, and ask staff the rest. Don't open cabinets or plug anything in.

| Item | Observed |
|---|---|
| Controller model (label) | |
| Teach pendant model | |
| Is a PC connected to the controller or cameras? What OS? | |
| Network: is the controller on a network? (ask; don't trace cables) | |
| Is a ROS 2 driver or other external motion interface installed? (ask) | |
| How have past demos sent motions to the arm? (ask) | |
| User frame / tool frame in use (UF0 330 mm above the base, UTOOL1 223 mm, per the twin) | |

## 8. Lighting

The twin was tuned to photos. Real lighting decides whether colour-based cube detection works.

- [ ] Photo from as close as possible to the table camera's position, under normal lighting, with the white sheet on the table
- [ ] The same shot with the cubes on the table, if allowed
- [ ] Light sources: ceiling type, windows (note the time of day), task lights
- [ ] Glare or reflections on the table or objects? Shadows from the arm?

## 9. Safety and access

- [ ] Fence, light curtain or e-stop locations (photo)
- [ ] Who supervises physical tests, and how to book a slot
- [ ] Rules for bringing printed fingers (review process, who approves)

## 10. Questions for staff (write down the answers)

1. How do planned motions reach the arm: the ROS 2 driver, a controller program loaded from waypoints, or something else?
2. Which gripper is installed, and are finger CAD (STEP) files available?
3. Can we get the camera calibration files (intrinsics, lens distortion, ArUco solves)?
4. Can we record real images from the table, side and wrist cameras for comparison with renders?
5. How many supervised test slots are there, and when?

## After the visit

- [ ] Commit this file and the photos (`docs/cell-recon/`)
- [ ] List every mismatch with the twin as an issue or note. Each is a sim-to-real gap to measure or report.
