# Pipeline contracts

What each stage of `fanuc_er4ia_sim/run_sort_pipeline.sh` reads and writes, field by field. Everything here was read from the starter code at the baseline commit; line references point into `fanuc_er4ia_sim/`.

Our sweep harness and the future real-arm export both depend on these formats. If the starter changes, update this file.

## Conventions

- **Units:** metres and degrees, unless a field name says otherwise (`_mm`, `_rad`).
- **Robot base frame:** the robot base origin sits at world `(0, 0, 0.90)`. Plan XY is world XY, because `camera.json` records `robot_base_xy: [0, 0]`.
- **Heights in `sort_plan.json`** (`pick_z`, `place_z`, `expected_centre_z`) are relative to the robot base plane, not to the world origin. The work surface is at `SURFACE_DZ = -0.0051` (5.1 mm below the base plane).
- **Heights in `ground_truth.json`, `scene_state.json` and `execution_report.json`** are world Z, so the work surface is at `0.8949`.
- **Image coordinates in `detections.json`** are normalised: x from 0 (left) to 1 (right), y from 0 (top) to 1 (bottom). This is marked by `"coordinate_convention": "unit"`.
- **Cube yaw** is symmetric every 90°. Errors are compared with `cube_pose.square_yaw`, which folds an angle into the ±45° range.
- **Joint 3:** the simulator uses relative joint angles. The real controller uses `sim_q3 = controller_J3 + J2`. That conversion belongs only in a future hardware export, never in the sim code (`docs/CALIBRATION_V05.md`).

## Stages

| # | Stage | Interpreter | Reads | Writes |
|---|---|---|---|---|
| 1 | `capture_scene.py --out RUN` | Isaac | `scene_config.py` (layout, cameras) | `world_camera.png`, `camera.json`, `ground_truth.json`, `scene_state.json` |
| 2 | `perceive.py --run RUN --stack-cubes` | Cosmos | `world_camera.png`, `camera.json`, Cosmos3-Nano weights | `detections.json`, `detections_raw.txt`, `detections_<colour>_audit_raw.txt`, `cube_inventory_crops/`, `cube_pose_crops/` |
| 3 | `plan_sort.py --run RUN` | Host | `detections.json`, `camera.json`, `world_camera.png`; then `ground_truth.json` **only after the plan is saved** | `sort_plan.json`, `perception_evaluation.json`, `detections_overlay.png` |
| 3b | inline check in `run_sort_pipeline.sh` | Host | `execution_report.json` | nothing; exits non-zero if the report is missing or `task_complete` is false |
| 4 | `sort_scene.py --run RUN` | Isaac | `sort_plan.json`, `scene_state.json`; `ground_truth.json` only after execution, for wide-cap scoring | `execution_events.json` (rewritten after every pick), `execution_report.json`, `frames/`, `side_frames/` |
| 5 | `encode_video.py` (×2) | Host | `frames/*.png`, `side_frames/*.png` | `sort_table.mp4`, `sort_side.mp4` |

The launcher uses `set -euo pipefail`, so the first stage that exits non-zero stops the run. Isaac can exit 0 after a Python exception (see "Failure signatures" below), so the launcher's step 3b checks the report file rather than trusting the exit code.

## Stage 1: capture

### `world_camera.png`

An RGB render from the table camera. For the cube task the resolution is doubled to **3840×2160** (`capture_scene.py:54`). Execution videos stay at 1920×1080.

### `camera.json` (read by `backproject.CameraModel`)

| Field | Type | Meaning |
|---|---|---|
| `camera` | str | `"table"` (or `"side"`, `"wrist"` with `--camera`) |
| `resolution` | [W, H] | Pixel size of `world_camera.png` |
| `focal_length_mm` | float | Read back from USD |
| `horizontal_aperture_mm`, `vertical_aperture_mm` | float | Sensor size; with the focal length, gives the field of view |
| `camera_to_world` | 4×4 list | Row-major USD matrix, row-vector convention (translation in the last row) |
| `table_top_z` | float | World Z of the calibrated work surface (`0.8949`) |
| `robot_base_xy` | [x, y] | Always `[0, 0]` |

`test_support.camera_model(cfg)` builds the same object from `scene_config.TABLE_CAM` without Isaac. We use it in host-only tests and the feasibility sweep.

### `ground_truth.json` (evaluation only, never for commands)

`{"objects": [...], "bins": {}}`. The objects are 6 cubes, 2 caps and 2 vials, built from `scene_config`, not from physics:

| Field | Cubes | Caps | Vials |
|---|---|---|---|
| `name` | `SortCube0..5` | `SortCap0..1` | `SortVial0..1` |
| `category` | `cube` | `cap` | `vial` |
| `colour` | `yellow`/`blue`/`red` | `yellow` | `clear` |
| `xyz` | `[x, y, edge/2]` | `[x, y, h/2]` | `[x, y, r]` |
| `size` | edge (0.010) | diameter | diameter |
| `yaw_deg` | from `SORT_CUBE_YAWS_DEG` | — | axis yaw |
| other | — | `orientation` | `length` |

The Z in `xyz` here is height above the surface, not world Z. Cube *i* is `scene_config.SORT_CUBES[i]`.

### `scene_state.json`

`{"objects": {"<prim name>": {"position": [x,y,z], "orientation": [w,x,y,z]}}}`. These are world poses read from the stage at capture time. `sort_scene.py` restores them so execution starts from exactly the captured layout. This is the simulator's own state, not an input to planning.

## Stage 2: perception (`detections.json`)

Top level: `objects` (list), `coordinate_convention: "unit"`, `model: "Cosmos3-Nano"`, `task: "cube_stack"`.

Perception has three passes:

1. **Whole-image detection.** The `STACK_PROMPT` is sent with the full image; the raw reply goes to `detections_raw.txt`.
2. **Colour audit.** `audit_stack_colours` runs for any colour that doesn't have exactly two detections. It first re-asks Cosmos about the whole image (`detections_<colour>_audit_raw.txt`). If that still doesn't give two, it falls back to image-only colour blobs that Cosmos must confirm crop by crop (`cube_inventory_crops/<colour>_candidate<i>.png` and `.txt`).
3. **Pose.** `inspect_cube_poses` fits a calibrated square silhouette to each cube. It sends Cosmos a crop plus that measurement and accepts the reported yaw only if all of these hold:
   - category and colour agree;
   - `0.8 ≤ pose_confidence ≤ 1`;
   - the reported yaw is within 3° of the measured yaw (mod 90).

Fields on each cube object:

| Field | Meaning |
|---|---|
| `label`, `category`, `colour`, `graspable` | From Cosmos |
| `center`, `bbox` | Normalised image coordinates; bbox is `[x_min, y_min, x_max, y_max]` |
| `detail_crop`, `category_confidence`, `localisation_source` | Only on cubes recovered by the blob fallback |
| `image_pose_measurement` | `{expected_colour, position_world_m, yaw_deg, roll_deg: 0, pitch_deg: 0, silhouette_iou, source, yaw_symmetry_deg: 90}`; also saved as `cube_pose_crops/cube_<i>_measurement.json` |
| `pose_source` | `"Cosmos_reports_calibrated_image_pose"` |
| `pose_confidence` | 0 unless Cosmos's answer passed the checks above |
| `pose_reason` | Cosmos's reason, or `"Image geometry fit is uncertain"` when silhouette IoU < 0.85 (in that case Cosmos is not asked) |
| `top_edge_endpoints` | Two normalised image points on the cube's top edge, or `null` when the pose was rejected |
| `cosmos_reported_yaw_deg`, `pose_world` | Only when accepted. `pose_world` is `{position_m, yaw_deg, roll_deg, pitch_deg, yaw_symmetry_deg}` |

`cube_pose_crops/cube_<i>.png` and `.txt` hold the 568×568 crop and the raw Cosmos reply for each cube.

If the first reply can't be parsed as JSON, `perceive.py` tries to salvage complete `{...}` entries. If nothing can be recovered, it **exits 1**.

## Stage 3: planning

### `sort_plan.json` (what the executor, and later the real-arm export, consumes)

| Field | Meaning |
|---|---|
| `source` | Must be `"Cosmos3-Nano"`; `sort_scene.validate_plan` rejects anything else |
| `gripper_model` | `"SMC MHZL2-16D2"` |
| `task` | `"cube_stack"` |
| `stack_ready` | true only when the eligible cubes are exactly 2 yellow, 2 blue and 2 red |
| `stack_colours_bottom_to_top` | `["yellow","yellow","blue","blue","red","red"]` |
| `open_gap_m` | `2 × JAW_OPEN` (0.012); the executor refuses a plan made for a different gripper opening |
| `picks` | Ordered pick list (below). Empty when `stack_ready` is false |
| `observations` | Every detection, with the fields below plus `eligible` and `skip_reason` |
| `skipped` | The subset of observations that were rejected |

Fields the planner adds to each observation:

- `detection_id`: index into `detections.json` `objects`
- `xy_raw`: back-projected centre, before refinement
- `localisation_method`: `refined`, `raw` or `rejected`
- `cosmos_yaw_deg`: yaw from `top_edge_endpoints`
- `pose_silhouette_iou`, `pose_refinement`: result of the bounded refinement (±20°, ±4 mm)
- `yaw_deg`: final yaw
- `spread_dir`: `[-sin(yaw), cos(yaw), 0]`, the world direction the jaws close along
- `pick_z`: `SURFACE_DZ + 0.0025`
- `jaw_half`: 0.005
- `xy`: final refined position

Each `picks[k]` is the observation plus:

| Field | Value |
|---|---|
| `stack_level` | 0–5, bottom to top |
| `place_xy` | `CUBE_STACK_XY` = `[0.28, 0.10]` |
| `place_z` | `SURFACE_DZ + level × 0.010 + 0.0025` |
| `expected_centre_z` | `SURFACE_DZ + (level + 0.5) × 0.010` |
| `place_spread_dir` | `[0, 1, 0]`; every cube is turned to a common yaw before placing |
| `place_yaw_deg` | 0 |

Within each colour, picks are ordered by `(x, y)`.

`skip_reason` values for the cube task:

- `not_a_cube`
- `cube_colour_unknown`
- `localisation_uncertain`: `refine_centre` did not return `refined`
- `cube_pose_low_confidence`: `pose_confidence < 0.8`
- `cube_pose_fit_uncertain`: refinement IoU < 0.75
- `cube_pose_missing_or_invalid`
- `outside_work_surface`
- `duplicate_detection`: within 12 mm of an earlier detection of the same category
- `invalid_detection`
- `incomplete_cube_colour_set`: set on every cube when the colour count is wrong

`plan_sort.py` **exits 0 even when `stack_ready` is false**. The run then stops in stage 4.

### `perception_evaluation.json` (scoring only)

The planned detections are matched one-to-one to the ground truth (Hungarian matching, an optimal one-to-one pairing on XY distance; pairs more than 25 mm apart are rejected).

- `matches[]`: one row per match, with `detection_id`, `name`, `category`, `position_error_mm`, `selected`, `expected_colour`, `predicted_colour`, `colour_correct`, and when yaw is present: `expected_yaw_deg`, `predicted_yaw_deg`, `yaw_error_deg_mod90`, `cosmos_yaw_error_deg_mod90`.
- `missed_objects`: ground-truth names with no match.
- `unmatched_detections`: detection ids with no match.
- Cap-only counters (always 0 for this task): `caps_matched`, `cap_orientations_correct`, `wide_caps_selected`, `cap_orientation_confusion`.

### `detections_overlay.png`

The capture with each observation drawn on it: green for eligible, red for skipped, the jaw closing direction in blue, and the yaw as text.

## Stage 4: execution

### Motion (`sort_scene.segments`)

Each pick is 11 segments:

1. `approach`
2. `descend`
3. `close`
4. `dwell`
5. `lift`
6. `carry`
7. `lower`
8. `release`
9. `settle`
10. `retreat`
11. `home`

Positions used:

- **Home:** `(0.30, 0.0, 0.24)` in the robot base frame.
- **Hover:** 0.13 m above the pick and place points.
- **Tool approach:** always straight down.
- **Tool offset:** `TOOL_LENGTH` = 0.293 m from the J6 wrist centre to the fingertip (equal to `cell.tip_offset()`).

Every 1/30 s frame is a separate `ik.solve` call. If that fails, the executor retries with `iters=500, damping=0.02`. Execution then **refuses to continue** when any of these hold:

- the solver reports failure;
- the fingertip is more than 1 mm from the target;
- the jaw direction is misaligned (|dot| ≤ 0.999).

### `execution_events.json`

A list of per-pick events, rewritten after each pick (so it survives a crash later in the run):

| Field | Meaning |
|---|---|
| `detection_id`, `category`, `stack_level`, `colour` | From the pick |
| `tracked_object` | Nearest simulator cube within 40 mm of the planned XY. Used for reporting only, never for motion |
| `perceived_yaw_deg`, `grasp_spread_dir`, `place_spread_dir` | Commanded wrist alignment |
| `initial_positions` | Poses of all objects before this pick |
| `phase_measurements.<descend\|dwell\|lift\|lower\|release>` | `actual_tip_robot_frame_m`, `commanded_tip_robot_frame_m`, `tip_error_mm`, `actual_spread_dir`, `commanded_spread_dir`, `wrist_joint_deg`, `object_centre_world_m` |
| `jaw_gap_mm` | Measured at `dwell` |
| `objects_lifted` | Objects that rose more than 25 mm |
| `pickup_verified` | `tracked_object` was among the lifted objects |
| `placement_error_mm` | XY distance from the cube to `place_xy` |
| `placement_yaw_error_deg_mod90`, `placement_tilt_deg`, `placement_pose_verified` | Placed pose: yaw under 8°, tilt under 5° |
| `placement_verified` | Pickup OK, XY within 3.33 mm, Z within 1.5 mm, and pose OK |
| `stack_support_verified` | `verify_cube_stack`: on site, correct layer height, each layer within 2.5 mm of the one below |
| `trajectory_ik_failures` | Number of IK failures |

The cube task **stops at the first pick** that fails placement or support.

### `execution_report.json` (the success record)

| Field | Meaning |
|---|---|
| `task_complete` | **The pass/fail flag.** True when there are picks, no abort, every pick ran, and every placement was verified |
| `verified_pickups`, `verified_placements` | Both must be 6 |
| `abort_reason` | null, or `"Cube tower stopped at level N: ..."` |
| `picks` | Same list as `execution_events.json` |
| `before`, `after` | Per-object `{position, orientation, centre, yaw_deg, tilt_deg}` |
| `frames`, `rendered` | Frame count; false with `--physics-only` |
| `task` | `"cube_stack"` |
| `hardware` | `gripper_model`, `jaw_stroke_m`, `open_gap_m`, `finger_length_m`, `cube_edge_m`, `cube_tip_clearance_m` |
| `wide_caps` | Wide-end-up caps disturbed (scored only after execution) |

## Stage 5: video

`encode_video.py --frames DIR --out FILE.mp4 --fps 30` encodes the sorted PNG frames with `imageio-ffmpeg`. It doesn't affect the result.

## Failure signatures

How to tell which stage failed, from the run folder alone. The sweep harness uses this table.

| First failing stage | What's on disk / in the log |
|---|---|
| Capture | No `camera.json` or `world_camera.png`. Log may show `Camera returned no image` |
| Perception: model or setup | No `detections.json`. Log shows a missing snapshot, a missing `transformers_cosmos3` or CUDA, or `FAILED to parse JSON` |
| Perception: inventory | `sort_plan.json` has `stack_ready: false`. `skip_reason` on the cubes says why: colour or count (`incomplete_cube_colour_set`, `cube_colour_unknown`) or pose (`cube_pose_*`, `localisation_uncertain`) |
| Planning | No `sort_plan.json` although `detections.json` exists (an exception in `plan_sort.py`) |
| Execution: plan rejected | Log shows `No eligible picks` or a `validate_plan` `ValueError`. This happens before Isaac starts, so the exit code is non-zero |
| Execution: IK | Log shows `IK failed: detection N, <segment>, frame i`. **No `execution_report.json`**, because the exception is raised before the report is written and Isaac may still exit 0. `execution_events.json` holds the picks completed before the failure |
| Execution: grasp | Report shows `pickup_verified: false` on the last pick |
| Execution: placement or stack | Report shows `pickup_verified: true` but `placement_verified` or `stack_support_verified` false. `abort_reason` names the level |
| Perception: colour swap | `task_complete: true`, but a placed cube's `tracked_object` has a different colour in `ground_truth.json` than the pick's planned `colour`. **The starter's report doesn't check colour**, so a swapped red and blue pair still reads as complete. `harness/run_sweep.py` scores this as `perception_colour` (evaluation only) |
| Success | `task_complete: true`, `verified_pickups: 6`, `verified_placements: 6`, and every placed cube has its planned colour |
