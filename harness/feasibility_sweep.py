"""Host-only kinematic feasibility sweep over cube layout seeds.

For each seed, build the layout with scene_config.hackathon_cubes(seed), give
the real planner ideal detections of that layout, and replay sort_scene.py's
frame-by-frame IK loop without Isaac. sort_scene seeds every IK call from the
previously commanded joints, never from physics, so an IK failure here is the
same IK failure the simulator would hit for that plan.

Offline analysis only: the ideal detections are built from configured layout
poses, and nothing produced here is ever fed back into the pipeline.
Not checked: physics (grasp, slip, stack support) and collisions.

    fanuc_er4ia_sim/.venv/bin/python harness/feasibility_sweep.py \
        --seeds 0-999 --out docs/results/feasibility
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

STARTER = Path(__file__).resolve().parents[1] / "fanuc_er4ia_sim"
sys.path.insert(0, str(STARTER))

import scene_config as C  # noqa: E402
import fk  # noqa: E402
import ik  # noqa: E402
from plan_sort import build_plan  # noqa: E402
from sort_scene import ease, segments, turn, validate_plan  # noqa: E402
from test_support import camera_model  # noqa: E402

FPS = 30
HOME = np.array([0.30, 0.0, 0.24])  # sort_scene.main
DOWN = [0.0, 0.0, -1.0]
LIMITS = np.deg2rad([C.JOINT_LIMITS_DEG[f"J{i}"] for i in range(1, 7)])
TOOL = tuple(np.array(C.TOOL_AXIS) * C.TOOL_LENGTH)  # == cell.tip_offset()


def parse_seeds(text):
    seeds = []
    for part in text.split(","):
        if "-" in part.strip()[1:]:
            lo, hi = part.split("-")
            seeds.extend(range(int(lo), int(hi) + 1))
        else:
            seeds.append(int(part))
    return seeds


def capture_camera():
    """Table camera as capture_scene.py renders it for the cube task (4K)."""
    cfg = dict(C.TABLE_CAM)
    cfg["resolution"] = tuple(2 * v for v in cfg["resolution"])
    return camera_model(cfg)


def ideal_detection(cam, x, y, colour, yaw):
    """Detection a perfect perception stage would report (same form as the tests)."""
    t = np.deg2rad(yaw)
    r = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    size = [cam.W, cam.H]
    top = cam.table_z + C.CUBE_EDGE
    ends = [
        (cam.project([*(np.array([x, y]) + r @ [a, -C.CUBE_EDGE / 2]), top]) / size)
        .tolist()
        for a in (-C.CUBE_EDGE / 2, C.CUBE_EDGE / 2)
    ]
    centre = cam.project([x, y, cam.table_z + C.CUBE_EDGE / 2]) / size
    return dict(
        label=f"{colour} cube",
        category="cube",
        colour=colour,
        center=centre.tolist(),
        top_edge_endpoints=ends,
        pose_confidence=0.95,
    )


def image_margin_px(cam, x, y, yaw):
    """Smallest distance from a cube's top corners to the image border."""
    t = np.deg2rad(yaw)
    r = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    half = C.CUBE_EDGE / 2
    margins = []
    for corner in ((-half, -half), (half, -half), (half, half), (-half, half)):
        u, v = cam.project([*(np.array([x, y]) + r @ corner), cam.table_z + C.CUBE_EDGE])
        margins.append(min(u, v, cam.W - u, cam.H - v))
    return float(min(margins))


def replay(plan):
    """sort_scene.main's motion loop, minus physics and rendering."""
    ik.set_tool_axis(C.TOOL_AXIS)
    ik.set_spread_axis(C.FINGER_SPREAD_AXIS)
    q = np.deg2rad([C.HOME_POSE_DEG[f"J{i}"] for i in range(1, 7)])
    q, ok = ik.solve(q, HOME, DOWN, LIMITS, tool_offset=TOOL)
    result = dict(
        ik_feasible=False,
        failed_level=None,
        failed_segment=None,
        failed_frame=None,
        ik_retries=0,
        max_tip_error_mm=0.0,
        min_limit_margin_deg=float("inf"),
        tightest_joint=None,
    )
    if not ok:
        result["failed_segment"] = "home"
        return result
    for pick in plan["picks"]:
        pick = dict(pick)
        if pick.get("spread_dir") is not None:
            r, _ = fk.fk(q)
            current = r @ np.array(C.FINGER_SPREAD_AXIS)
            spread = np.array(pick["spread_dir"], float)
            if np.dot(current, spread) < 0:
                spread = -spread
            pick["spread_dir"] = spread.tolist()
            if pick.get("place_spread_dir") is not None:
                destination = np.array(pick["place_spread_dir"], float)
                if np.dot(spread, destination) < 0:
                    destination = -destination
                pick["place_spread_dir"] = destination.tolist()
        for name, p0, p1, duration, _, _, spread in segments(pick, HOME):
            spread_start = None
            if spread is not None and name in ("approach", "carry"):
                r, _ = fk.fk(q)
                s = r @ np.array(C.FINGER_SPREAD_AXIS)
                s[2] = 0
                s /= np.linalg.norm(s)
                spread = np.array(spread, float)
                spread_start = s
            n = round(duration * FPS)
            for i in range(n):
                t = ease((i + 1) / n)
                target = p0 + (p1 - p0) * t
                direction = (
                    turn(spread_start, spread, t) if spread_start is not None else spread
                )
                q, ok = ik.solve(
                    q, target, DOWN, LIMITS, tool_offset=TOOL, spread_dir=direction
                )
                if not ok:
                    result["ik_retries"] += 1
                    q, ok = ik.solve(
                        q,
                        target,
                        DOWN,
                        LIMITS,
                        tool_offset=TOOL,
                        spread_dir=direction,
                        iters=500,
                        damping=0.02,
                    )
                r, actual = fk.tool_pose(q, TOOL)
                error = np.linalg.norm(actual - target)
                aligned = (
                    direction is None
                    or abs(np.dot(r @ np.array(C.FINGER_SPREAD_AXIS), direction)) > 0.999
                )
                result["max_tip_error_mm"] = max(result["max_tip_error_mm"], error * 1000)
                margins = np.degrees(np.minimum(q - LIMITS[:, 0], LIMITS[:, 1] - q))
                j = int(np.argmin(margins))
                if margins[j] < result["min_limit_margin_deg"]:
                    result["min_limit_margin_deg"] = float(margins[j])
                    result["tightest_joint"] = f"J{j + 1}"
                if not ok or error > 0.001 or not aligned:
                    result.update(
                        failed_level=pick.get("stack_level"),
                        failed_segment=name,
                        failed_frame=i,
                    )
                    return result
    result["ik_feasible"] = True
    return result


def check_seed(seed, cam, yaw_offset_deg=0.0):
    row = dict(seed=seed, yaw_offset_deg=yaw_offset_deg)
    try:
        cubes = C.hackathon_cubes(seed)
    except ValueError as exc:
        return dict(row, feasible=False, stage="layout", detail=str(exc))
    yaws = [a + yaw_offset_deg for a in C.SORT_CUBE_YAWS_DEG]
    row["cube_xy"] = ";".join(f"{c}:{x:.4f},{y:.4f}" for x, y, c in cubes)
    row["min_image_margin_px"] = round(
        min(image_margin_px(cam, x, y, a) for (x, y, _), a in zip(cubes, yaws)), 1
    )
    if row["min_image_margin_px"] <= 0:
        return dict(row, feasible=False, stage="camera", detail="cube outside image")
    det = {
        "objects": [ideal_detection(cam, x, y, c, a) for (x, y, c), a in zip(cubes, yaws)],
        "coordinate_convention": "unit",
    }
    plan = build_plan(det, cam, task="cube_stack")
    if not plan["stack_ready"]:
        reasons = sorted({o["skip_reason"] for o in plan["skipped"]})
        return dict(row, feasible=False, stage="plan", detail=",".join(reasons))
    try:
        validate_plan(plan)
    except ValueError as exc:
        return dict(row, feasible=False, stage="validate_plan", detail=str(exc))
    motion = replay(plan)
    row.update(motion)
    row["min_limit_margin_deg"] = round(row["min_limit_margin_deg"], 2)
    row["max_tip_error_mm"] = round(row["max_tip_error_mm"], 4)
    if not motion["ik_feasible"]:
        detail = (
            f"level {motion['failed_level']}, {motion['failed_segment']}, "
            f"frame {motion['failed_frame']}"
        )
        return dict(row, feasible=False, stage="ik", detail=detail)
    return dict(row, feasible=True, stage="", detail="")


FIELDS = [
    "seed",
    "yaw_offset_deg",
    "feasible",
    "stage",
    "detail",
    "min_image_margin_px",
    "ik_retries",
    "max_tip_error_mm",
    "min_limit_margin_deg",
    "tightest_joint",
    "seconds",
    "cube_xy",
]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seeds", default=f"0-199,{C.CUBE_LAYOUT_SEED}")
    ap.add_argument(
        "--yaw-offsets",
        default="0",
        help="comma-separated yaw perturbations in degrees, e.g. 0,-3,3",
    )
    ap.add_argument("--out", required=True, help="directory for results.csv")
    a = ap.parse_args()
    cam = capture_camera()
    offsets = [float(v) for v in a.yaw_offsets.split(",")]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for seed in parse_seeds(a.seeds):
        for offset in offsets:
            start = time.perf_counter()
            row = check_seed(seed, cam, offset)
            row["seconds"] = round(time.perf_counter() - start, 2)
            rows.append(row)
            status = "ok" if row["feasible"] else f'FAIL {row["stage"]}: {row["detail"]}'
            print(f"seed {seed} yaw{offset:+.0f}: {status}", flush=True)
    with open(out / "results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    failed = [r for r in rows if not r["feasible"]]
    summary = dict(
        checked=len(rows),
        feasible=len(rows) - len(failed),
        infeasible=[(r["seed"], r["yaw_offset_deg"], r["stage"], r["detail"]) for r in failed],
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f'{summary["feasible"]}/{summary["checked"]} feasible; results in {out}')


if __name__ == "__main__":
    main()
