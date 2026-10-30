"""Check that focused Cosmos replies preserve coordinates across colour groups."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import json
import re
import cv2
import numpy as np
import scene_config as C
from test_support import camera_model
from perceive import (
    CUBE_POSE_PROMPT,
    audit_stack_colours,
    crop_to_image,
    parse_json,
    work_surface_crop,
)


class CubePerceptionTests(unittest.TestCase):
    def test_mixed_coordinate_replies_are_normalized_before_merging(self):
        parsed = {
            "objects": [
                dict(
                    category="cube",
                    colour=colour,
                    center=[x, 500],
                    bbox=[x - 5, 490, x + 5, 510],
                )
                for colour, x in [
                    ("blue", 300),
                    ("blue", 400),
                    ("red", 600),
                    ("red", 700),
                ]
            ]
        }
        reply = {
            "objects": [
                dict(
                    category="cube",
                    colour="yellow",
                    center=[x, 0.8],
                    bbox=[x - 0.01, 0.78, x + 0.01, 0.82],
                )
                for x in (0.2, 0.5)
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            img = root / "camera.png"
            cv2.imwrite(str(img), np.zeros((1080, 1920, 3), np.uint8))
            with patch("perceive.ask", return_value=json.dumps(reply)) as ask:
                result = audit_stack_colours(None, None, img, parsed, root)
            self.assertEqual(ask.call_count, 1)
        self.assertEqual(len(result["objects"]), 6)
        self.assertEqual(result["coordinate_convention"], "unit")
        self.assertAlmostEqual(result["objects"][0]["center"][0], 0.3)
        self.assertAlmostEqual(result["objects"][-1]["center"][0], 0.5)
        self.assertTrue(all(0 <= v <= 1 for o in result["objects"] for v in o["bbox"]))

    def test_empty_colour_reply_does_not_fabricate_cubes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            img = root / "camera.png"
            cv2.imwrite(str(img), np.zeros((100, 100, 3), np.uint8))
            with patch("perceive.ask", return_value='{"objects":[]}'):
                result = audit_stack_colours(None, None, img, {"objects": []}, root)
        self.assertEqual(result["objects"], [])

    def test_model_can_return_bare_detection_array(self):
        self.assertEqual(
            parse_json('```json\n[{"category":"cube"}]\n```'),
            {"objects": [{"category": "cube"}]},
        )

    def test_detection_crop_keeps_layout_and_drops_parked_gripper(self):
        # Cosmos labelled the parked gripper (top of the image) as cubes.
        cam = camera_model(C.TABLE_CAM)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            img = root / "world_camera.png"
            cv2.imwrite(str(img), np.zeros((cam.H, cam.W, 3), np.uint8))
            (root / "camera.json").write_text(json.dumps(cam.j))
            path, (x0, y0, cw, ch) = work_surface_crop(img, root)
            self.assertEqual(cv2.imread(str(path)).shape[:2], (ch, cw))
        self.assertGreater(y0, 0.3 * cam.H)
        for x, y, _ in C.SORT_CUBES:
            u, v = cam.project([x, y, cam.table_z + C.CUBE_EDGE / 2])
            self.assertTrue(x0 <= u <= x0 + cw and y0 <= v <= y0 + ch)

    def test_crop_detections_map_back_to_full_image(self):
        objects = [dict(category="cube", center=[500, 500], bbox=[0, 0, 1000, 1000])]
        result = crop_to_image(objects, (400, 1000, 2000, 1000), 4000, 2000)
        np.testing.assert_allclose(result[0]["center"], [0.35, 0.75])
        np.testing.assert_allclose(result[0]["bbox"], [0.1, 0.5, 0.6, 1.0])

    def test_cube_pose_prompt_has_no_example_yaw_to_copy(self):
        # Cosmos echoed the old example yaw (14.2) instead of the measured one.
        self.assertIsNone(re.search(r'"yaw_deg"\s*:\s*-?\d', CUBE_POSE_PROMPT))
        self.assertIn("<measured yaw_deg>", CUBE_POSE_PROMPT)


if __name__ == "__main__":
    unittest.main()
