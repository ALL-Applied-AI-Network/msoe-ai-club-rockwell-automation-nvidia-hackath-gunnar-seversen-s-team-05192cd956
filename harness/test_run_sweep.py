"""Sweep harness tests on mocked run directories and fake stage interpreters.

    fanuc_er4ia_sim/.venv/bin/python -m unittest discover -s harness
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_sweep  # noqa: E402

COLOURS = ["yellow", "yellow", "blue", "blue", "red", "red"]


def ground_truth():
    return {
        "objects": [
            {"name": f"SortCube{i}", "category": "cube", "colour": c}
            for i, c in enumerate(COLOURS)
        ]
    }


def event(level, tracked=None, colour=None, pickup=True, placed=True, support=True):
    return {
        "stack_level": level,
        "colour": colour or COLOURS[level],
        "tracked_object": tracked or f"SortCube{level}",
        "pickup_verified": pickup,
        "placement_verified": placed,
        "stack_support_verified": support,
        "placement_error_mm": 0.4,
        "placement_yaw_error_deg_mod90": 1.5,
    }


def report(events, complete):
    return {
        "task_complete": complete,
        "verified_pickups": sum(e["pickup_verified"] for e in events),
        "verified_placements": sum(e["placement_verified"] for e in events),
        "abort_reason": None if complete else "Cube tower stopped",
        "picks": events,
    }


def write(run, name, data):
    path = run / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data))


def make_run(run, upto, plan_ready=True, report_data=None, execute_log=""):
    """Fake run folder holding every file up to (and including) stage `upto`."""
    run.mkdir(parents=True, exist_ok=True)
    level = ["capture", "perceive", "plan", "execute"].index(upto)
    write(run, "camera.json", {"resolution": [3840, 2160]})
    write(run, "world_camera.png", "png")
    write(run, "ground_truth.json", ground_truth())
    if level >= 1:
        write(run, "detections.json", {"objects": []})
    if level >= 2:
        skipped = [] if plan_ready else [{"skip_reason": "incomplete_cube_colour_set"}]
        write(run, "sort_plan.json", {"stack_ready": plan_ready, "skipped": skipped})
        write(run, "perception_evaluation.json", {
            "matches": [
                {"category": "cube", "colour_correct": True, "position_error_mm": 0.2,
                 "yaw_error_deg_mod90": 1.0}
                for _ in COLOURS
            ]
        })
    if level >= 3:
        if report_data is not None:
            write(run, "execution_report.json", report_data)
        write(run, "logs/execute.log", execute_log)


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "seed_1"

    def outcome(self, stopped=None):
        return run_sweep.classify(self.run_dir, stopped)

    def test_success_requires_complete_report_and_true_colours(self):
        make_run(self.run_dir, "execute", report_data=report([event(i) for i in range(6)], True))
        self.assertEqual(self.outcome(), ("success", ""))

    def test_swapped_colours_fail_even_when_simulator_reports_complete(self):
        events = [event(i) for i in range(6)]
        events[2]["tracked_object"], events[4]["tracked_object"] = "SortCube4", "SortCube2"
        make_run(self.run_dir, "execute", report_data=report(events, True))
        self.assertEqual(self.outcome(), ("perception_colour", "wrong colour at levels [2, 4]"))

    def test_missing_capture_outputs(self):
        self.run_dir.mkdir()
        self.assertEqual(self.outcome(("capture", 1))[0], "capture")

    def test_perception_setup_failure_reports_log_line(self):
        make_run(self.run_dir, "capture")
        write(self.run_dir, "logs/perceive.log", "loading\nCosmos3-Nano not found under /x\n")
        self.assertEqual(self.outcome(("perceive", 1)), ("perception_setup", "Cosmos3-Nano not found under /x"))

    def test_planner_crash(self):
        make_run(self.run_dir, "perceive")
        self.assertEqual(self.outcome(("plan", 1))[0], "planning")

    def test_incomplete_inventory_is_a_perception_failure(self):
        make_run(self.run_dir, "plan", plan_ready=False)
        self.assertEqual(self.outcome(("execute", 1)), ("perception", "incomplete_cube_colour_set"))

    def test_ik_failure_without_report_even_after_zero_exit(self):
        log = "Traceback\nRuntimeError: IK failed: detection 3, descend, frame 4; refusing off-target descent\n"
        make_run(self.run_dir, "execute", execute_log=log)
        outcome, detail = self.outcome(None)
        self.assertEqual(outcome, "execution_ik")
        self.assertIn("detection 3, descend", detail)

    def test_rejected_plan(self):
        make_run(self.run_dir, "execute", execute_log="ValueError: Tower repeats a cube detection\n")
        self.assertEqual(self.outcome(("execute", 1))[0], "plan_rejected")

    def test_grasp_placement_and_support_failures_name_the_level(self):
        cases = [
            (dict(pickup=False, placed=False), "grasp"),
            (dict(placed=False), "placement"),
            (dict(support=False), "stack_support"),
        ]
        for kwargs, expected in cases:
            with self.subTest(expected=expected):
                events = [event(0), event(1, **kwargs)]
                make_run(self.run_dir, "execute", report_data=report(events, False))
                self.assertEqual(self.outcome(), (expected, "level 1"))

    def test_timeout(self):
        make_run(self.run_dir, "capture")
        self.assertEqual(self.outcome(("perceive", "timeout"))[0], "timeout_perceive")

    def test_metrics_read_report_and_evaluation(self):
        make_run(self.run_dir, "execute", report_data=report([event(i) for i in range(6)], True))
        m = run_sweep.metrics(self.run_dir)
        self.assertEqual(m["verified_placements"], 6)
        self.assertEqual(m["colours_correct"], 6)
        self.assertEqual(m["max_place_error_mm"], 0.4)
        self.assertEqual(m["max_perception_yaw_deg"], 1.0)


FAKE_STAGE = textwrap.dedent(
    """\
    #!{python}
    # Fake Isaac/Cosmos/host interpreter: acts out one starter stage.
    import json, os, sys
    from pathlib import Path
    script, args = Path(sys.argv[1]).name, sys.argv[2:]
    if script == "encode_video.py":
        Path(args[args.index("--out") + 1]).write_text("mp4")
        sys.exit(0)
    run = Path(args[args.index("--run" if "--run" in args else "--out") + 1])
    seed = os.environ["CUBE_LAYOUT_SEED"]
    mode = dict(m.split(":") for m in os.environ["FAKE_MODES"].split(",")).get(seed, "success")
    colours = {colours}
    def put(name, data):
        (run / name).write_text(json.dumps(data))
    with open(run / "argv.log", "a") as f:
        f.write(script + " " + " ".join(args) + "\\n")
    if script == "capture_scene.py":
        put("camera.json", {{"resolution": [3840, 2160]}})
        (run / "world_camera.png").write_text("png")
        put("ground_truth.json", {{"objects": [
            {{"name": f"SortCube{{i}}", "category": "cube", "colour": c}} for i, c in enumerate(colours)]}})
        put("scene_state.json", {{"objects": {{}}}})
        (run / "seed.txt").write_text(seed)
    elif script == "perceive.py":
        if mode == "no_model":
            print("Cosmos3-Nano not found under /nowhere"); sys.exit(1)
        put("detections.json", {{"objects": []}})
    elif script == "plan_sort.py":
        put("sort_plan.json", {{"stack_ready": mode != "inventory",
            "skipped": [] if mode != "inventory" else [{{"skip_reason": "cube_colour_unknown"}}]}})
    elif script == "sort_scene.py":
        if mode == "inventory":
            print("No eligible picks"); sys.exit(1)
        if mode == "ik":
            print("RuntimeError: IK failed: detection 2, carry, frame 9; refusing off-target descent")
            sys.exit(0)  # Isaac can exit 0 after an exception
        events = [{{"stack_level": i, "colour": c, "tracked_object": f"SortCube{{i}}",
                    "pickup_verified": True, "placement_verified": True,
                    "stack_support_verified": True, "placement_error_mm": 0.3}}
                  for i, c in enumerate(colours)]
        put("execution_report.json", {{"task_complete": True, "verified_pickups": 6,
            "verified_placements": 6, "abort_reason": None, "picks": events}})
        if "--physics-only" not in args:
            (run / "frames").mkdir(exist_ok=True)
    """
)


class EndToEndTests(unittest.TestCase):
    """`run` and `summarize` against fake interpreters, as on a GPU box."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        fake = self.tmp / "fake_stage"
        fake.write_text(FAKE_STAGE.format(python=sys.executable, colours=COLOURS))
        fake.chmod(0o755)
        isaac = self.tmp / "isaacsim"
        isaac.mkdir()
        (isaac / "python.sh").symlink_to(fake)
        self.env = dict(
            os.environ,
            ISAAC=str(isaac),
            COSMOS=str(fake),
            HOST_PYTHON=str(fake),
            FAKE_MODES="2:ik,3:inventory,4:no_model",
        )
        self.env.pop("CUBE_LAYOUT_SEED", None)
        self.out = self.tmp / "sweep"

    def sweep(self, *extra):
        return subprocess.run(
            [sys.executable, str(Path(run_sweep.__file__)), "run", str(self.out), *extra],
            env=self.env, capture_output=True, text=True,
        )

    def result(self, seed):
        return json.loads((self.out / f"seed_{seed}" / run_sweep.RESULT).read_text())

    def test_sweep_classifies_each_seed_and_writes_summaries(self):
        done = self.sweep("--seeds", "1,2,3,4", "--usd-per-hour", "3")
        self.assertEqual(done.returncode, 0, done.stderr)
        outcomes = {s: self.result(s)["outcome"] for s in (1, 2, 3, 4)}
        self.assertEqual(
            outcomes,
            {1: "success", 2: "execution_ik", 3: "perception", 4: "perception_setup"},
        )
        for seed in (1, 2, 3, 4):
            self.assertEqual((self.out / f"seed_{seed}" / "seed.txt").read_text(), str(seed))
        self.assertIn("--physics-only", (self.out / "seed_1" / "argv.log").read_text())
        self.assertNotIn("execute", self.result(4)["stage_seconds"])
        md = (self.out / "summary.md").read_text()
        self.assertIn("**Task success: 1/4 (25%)**", md)
        self.assertIn("| execution_ik | 1 |", md)
        self.assertIn("at $3.0/h", md)
        csv_lines = (self.out / "summary.csv").read_text().splitlines()
        self.assertEqual(len(csv_lines), 5)

    def test_rerun_resumes_and_replaces_partial_runs(self):
        self.sweep("--seeds", "1")
        (self.out / "seed_5").mkdir()  # interrupted earlier, no result
        before = self.result(1)
        done = self.sweep("--seeds", "1,5")
        self.assertIn("seed 1: already done", done.stdout)
        self.assertEqual(self.result(1), before)
        self.assertEqual(self.result(5)["outcome"], "success")
        self.assertEqual(len(list(self.out.glob("seed_5.incomplete.*"))), 1)

    def test_render_encodes_both_videos(self):
        done = self.sweep("--seeds", "1", "--render")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.out / "seed_1" / "sort_table.mp4").is_file())
        self.assertTrue((self.out / "seed_1" / "sort_side.mp4").is_file())

    def test_missing_interpreter_is_reported_before_any_run(self):
        self.env["COSMOS"] = str(self.tmp / "nope")
        done = self.sweep("--seeds", "1")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("missing or not executable", done.stderr)
        self.assertFalse(self.out.exists())


class CommandContractTests(unittest.TestCase):
    """Every flag the harness passes must exist in the real starter script."""

    def test_flags_exist_in_starter_scripts(self):
        run = Path("/run")
        commands = run_sweep.stage_commands(run, "/isaac", "/cosmos", "/host", render=True)
        steps = [c for s, c in commands.items() if s != "video"] + commands["video"]
        for cmd in steps:
            source = Path(cmd[1]).read_text()
            for flag in (a for a in cmd[2:] if a.startswith("--")):
                with self.subTest(script=Path(cmd[1]).name, flag=flag):
                    self.assertIn(f'"{flag}"', source)
        source = (run_sweep.STARTER / "sort_scene.py").read_text()
        self.assertIn('"--physics-only"', source)

    def test_seed_sets_are_disjoint_and_include_the_reference_layout(self):
        sets = json.loads(run_sweep.SEEDS_FILE.read_text())
        dev, heldout = set(sets["dev"]["seeds"]), set(sets["heldout"]["seeds"])
        self.assertFalse(dev & heldout)
        self.assertIn(20261009, dev)


if __name__ == "__main__":
    unittest.main()
