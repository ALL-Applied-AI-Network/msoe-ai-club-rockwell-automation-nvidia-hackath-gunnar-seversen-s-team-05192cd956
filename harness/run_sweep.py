"""Run the starter pipeline across layout seeds and summarise the results.

Runs the same stages as fanuc_er4ia_sim/run_sort_pipeline.sh, one seed per run
directory, timing each stage and classifying the first stage that failed (see
docs/pipeline.md, "Failure signatures").

    export ISAAC=/path/to/isaacsim COSMOS=/path/to/cosmos/bin/python
    fanuc_er4ia_sim/.venv/bin/python harness/run_sweep.py run --set dev sweeps/dev
    fanuc_er4ia_sim/.venv/bin/python harness/run_sweep.py summarize sweeps/dev

`run` resumes: seeds that already have harness_result.json are skipped.
Ground truth is read only to score finished runs, never to change them.
"""

import argparse
import csv
import json
import os
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STARTER = ROOT / "fanuc_er4ia_sim"
SEEDS_FILE = Path(__file__).resolve().parent / "seeds.json"
STAGES = ("capture", "perceive", "plan", "execute", "video")
RESULT = "harness_result.json"


def stage_commands(run, isaac, cosmos, host, render):
    py = str(Path(isaac) / "python.sh")
    execute = [py, str(STARTER / "sort_scene.py"), "--run", str(run)]
    if not render:
        execute.append("--physics-only")
    commands = {
        "capture": [py, str(STARTER / "capture_scene.py"), "--out", str(run)],
        "perceive": [cosmos, str(STARTER / "perceive.py"), "--run", str(run), "--stack-cubes"],
        "plan": [host, str(STARTER / "plan_sort.py"), "--run", str(run)],
        "execute": execute,
    }
    if render:
        commands["video"] = [
            [host, str(STARTER / "encode_video.py"), "--frames", str(run / frames),
             "--out", str(run / out), "--fps", "30"]
            for frames, out in (("frames", "sort_table.mp4"), ("side_frames", "sort_side.mp4"))
        ]
    return commands


def run_seed(seed, run, commands, timeout):
    """Run stages in order, stopping at the first non-zero exit (like set -e)."""
    logs = run / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, CUBE_LAYOUT_SEED=str(seed))
    seconds, stopped = {}, None
    for stage in STAGES:
        if stage not in commands:
            continue
        steps = commands[stage] if stage == "video" else [commands[stage]]
        start = time.perf_counter()
        with open(logs / f"{stage}.log", "w") as log:
            for cmd in steps:
                try:
                    code = subprocess.run(
                        cmd, cwd=STARTER, env=env, stdout=log,
                        stderr=subprocess.STDOUT, timeout=timeout,
                    ).returncode
                except subprocess.TimeoutExpired:
                    code = "timeout"
                if code != 0:
                    stopped = (stage, code)
                    break
        seconds[stage] = round(time.perf_counter() - start, 1)
        if stopped:
            break
    return seconds, stopped


def _read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _log_line(run, stage, *needles):
    """Last log line containing any needle, for a human-readable failure detail."""
    try:
        lines = (run / "logs" / f"{stage}.log").read_text(errors="replace").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        if any(n in line for n in needles):
            return line.strip()[:200]
    return lines[-1].strip()[:200] if lines else ""


def classify(run, stopped=None):
    """First failing stage from the run directory alone. Returns (outcome, detail)."""
    if stopped and stopped[1] == "timeout":
        return f"timeout_{stopped[0]}", ""
    if not (run / "camera.json").is_file() or not (run / "world_camera.png").is_file():
        return "capture", _log_line(run, "capture", "Error", "error")
    if not (run / "detections.json").is_file():
        return "perception_setup", _log_line(
            run, "perceive", "FAILED", "Error", "error", "not found", "missing"
        )
    plan = _read(run / "sort_plan.json")
    if plan is None:
        return "planning", _log_line(run, "plan", "Error", "error")
    if not plan.get("stack_ready"):
        reasons = sorted({o.get("skip_reason") for o in plan.get("skipped", []) if o.get("skip_reason")})
        return "perception", ",".join(reasons)
    report = _read(run / "execution_report.json")
    if report is None:
        line = _log_line(run, "execute", "IK failed", "Error", "error")
        if "IK failed" in line:
            return "execution_ik", line
        # validate_plan raises ValueError before Isaac starts.
        return ("plan_rejected" if "ValueError" in line else "execution_crash"), line
    if report.get("task_complete"):
        wrong = wrong_colours(run, report)
        return ("perception_colour", f"wrong colour at levels {wrong}") if wrong else ("success", "")
    last = (report.get("picks") or [{}])[-1]
    level = last.get("stack_level")
    if not last.get("pickup_verified"):
        return "grasp", f"level {level}"
    if not last.get("placement_verified"):
        return "placement", f"level {level}"
    if not last.get("stack_support_verified", True):
        return "stack_support", f"level {level}"
    return "execution_other", str(report.get("abort_reason") or "")


def wrong_colours(run, report):
    """Scoring only: stack levels whose placed cube is not the planned colour."""
    gt = _read(run / "ground_truth.json") or {}
    truth = {o["name"]: o.get("colour") for o in gt.get("objects", [])}
    return [
        e.get("stack_level")
        for e in report.get("picks", [])
        if "stack_level" in e and truth.get(e.get("tracked_object")) != e.get("colour")
    ]


def metrics(run):
    out = {}
    report = _read(run / "execution_report.json") or {}
    for key in ("task_complete", "verified_pickups", "verified_placements", "abort_reason"):
        out[key] = report.get(key)
    picks = report.get("picks", [])
    place = [e["placement_error_mm"] for e in picks if "placement_error_mm" in e]
    place_yaw = [e["placement_yaw_error_deg_mod90"] for e in picks if "placement_yaw_error_deg_mod90" in e]
    out["max_place_error_mm"] = round(max(place), 3) if place else None
    out["max_place_yaw_deg"] = round(max(place_yaw), 2) if place_yaw else None
    evaluation = _read(run / "perception_evaluation.json") or {}
    matches = [m for m in evaluation.get("matches", []) if m.get("category") == "cube"]
    out["cubes_matched"] = len(matches) if evaluation else None
    out["colours_correct"] = sum(bool(m.get("colour_correct")) for m in matches) if evaluation else None
    pos = [m["position_error_mm"] for m in matches]
    yaw = [m["yaw_error_deg_mod90"] for m in matches if "yaw_error_deg_mod90" in m]
    out["max_perception_error_mm"] = round(max(pos), 3) if pos else None
    out["max_perception_yaw_deg"] = round(max(yaw), 2) if yaw else None
    return out


def gpu_name():
    try:
        return subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def git_commit():
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def resolve_seeds(args):
    if args.seeds:
        return [int(s) for s in args.seeds.split(",")]
    return json.loads(SEEDS_FILE.read_text())[args.set]["seeds"]


def cmd_run(args):
    isaac = os.environ.get("ISAAC", "/isaacsim")
    cosmos = os.environ.get("COSMOS")
    host = os.environ.get("HOST_PYTHON", str(STARTER / ".venv" / "bin" / "python"))
    if not cosmos:
        raise SystemExit("Set COSMOS to the Python interpreter in your Cosmos environment")
    for exe in (Path(isaac) / "python.sh", Path(cosmos), Path(host)):
        if not os.access(exe, os.X_OK):
            raise SystemExit(f"Python launcher missing or not executable: {exe}")
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    seeds = resolve_seeds(args)
    meta = dict(
        started_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        seed_set=None if args.seeds else args.set,
        seeds=seeds,
        git_commit=git_commit(),
        gpu=gpu_name(),
        render=args.render,
        usd_per_hour=args.usd_per_hour,
    )
    (out / "sweep.json").write_text(json.dumps(meta, indent=2) + "\n")
    for seed in seeds:
        run = out / f"seed_{seed}"
        if (run / RESULT).is_file():
            print(f"seed {seed}: already done, skipping", flush=True)
            continue
        if run.exists():
            run.rename(out / f"seed_{seed}.incomplete.{int(time.time())}")
        run.mkdir()
        commands = stage_commands(run, isaac, cosmos, host, args.render)
        start = time.perf_counter()
        seconds, stopped = run_seed(seed, run, commands, args.timeout)
        outcome, detail = classify(run, stopped)
        result = dict(
            seed=seed,
            outcome=outcome,
            detail=detail,
            exit=dict(stage=stopped[0], code=stopped[1]) if stopped else None,
            stage_seconds=seconds,
            total_seconds=round(time.perf_counter() - start, 1),
            **metrics(run),
        )
        (run / RESULT).write_text(json.dumps(result, indent=2) + "\n")
        print(f"seed {seed}: {outcome} {detail} ({result['total_seconds']} s)", flush=True)
    cmd_summarize(args)


COLUMNS = [
    "seed", "outcome", "detail", "verified_pickups", "verified_placements",
    "colours_correct", "max_perception_error_mm", "max_perception_yaw_deg",
    "max_place_error_mm", "max_place_yaw_deg", "total_seconds",
] + [f"{s}_s" for s in STAGES]


def cmd_summarize(args):
    out = Path(args.out).resolve()
    meta = _read(out / "sweep.json") or {}
    results = sorted(
        (r for r in (_read(p) for p in out.glob(f"seed_*/{RESULT}")) if r),
        key=lambda r: r["seed"],
    )
    rows = [dict(r, **{f"{s}_s": r["stage_seconds"].get(s) for s in STAGES}) for r in results]
    with open(out / "summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (out / "summary.md").write_text(render_markdown(meta, rows))
    print(f"{len(rows)} runs summarised in {out / 'summary.md'}")


def render_markdown(meta, rows):
    n = len(rows)
    ok = sum(r["outcome"] == "success" for r in rows)
    lines = [
        "# Sweep summary",
        "",
        f"- Seed set: {meta.get('seed_set') or 'custom'} ({n} of {len(meta.get('seeds', []))} seeds finished)",
        f"- Commit: {meta.get('git_commit')}; GPU: {meta.get('gpu')}; rendered: {meta.get('render')}",
        f"- Started (UTC): {meta.get('started_utc')}",
        f"- **Task success: {ok}/{n}" + (f" ({100 * ok / n:.0f}%)**" if n else "**"),
        "",
        "## First failing stage",
        "",
        "| Outcome | Runs |",
        "|---|---|",
    ]
    counts = {}
    for r in rows:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    lines += [f"| {k} | {v} |" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]
    lines += ["", "## Time per stage (seconds)", "", "| Stage | Median | Max |", "|---|---|---|"]
    for stage in STAGES + ("total",):
        key = "total_seconds" if stage == "total" else f"{stage}_s"
        values = [r[key] for r in rows if r.get(key) is not None]
        if values:
            lines.append(f"| {stage} | {statistics.median(values):.1f} | {max(values):.1f} |")
    hours = sum(r["total_seconds"] for r in rows) / 3600
    rate = meta.get("usd_per_hour")
    lines += ["", f"GPU time: {hours:.2f} h" + (f", about ${hours * rate:.2f} at ${rate}/h" if rate else ""), ""]
    lines += ["## Runs", "", "| " + " | ".join(COLUMNS[:11]) + " |", "|" + "---|" * 11]
    for r in rows:
        lines.append("| " + " | ".join("" if r.get(c) is None else str(r.get(c)) for c in COLUMNS[:11]) + " |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the pipeline for each seed, then summarise")
    run.add_argument("out", help="sweep directory; one seed_<n>/ run folder per seed")
    run.add_argument("--set", default="dev", choices=["dev", "heldout"])
    run.add_argument("--seeds", help="comma-separated seeds instead of --set")
    run.add_argument("--render", action="store_true", help="render frames and videos (slower)")
    run.add_argument("--timeout", type=int, default=1800, help="seconds per stage")
    run.add_argument("--usd-per-hour", type=float, default=None, help="GPU price, for the cost line")
    run.set_defaults(func=cmd_run)
    summarize = sub.add_parser("summarize", help="rebuild summary.csv and summary.md")
    summarize.add_argument("out")
    summarize.set_defaults(func=cmd_summarize)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
