"""try_cosmos_api.py against a local fake of the OpenAI-style chat endpoint."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import cv2
import numpy as np

SCRIPT = Path(__file__).resolve().parent / "try_cosmos_api.py"
REPLY = """```json
{"objects":[{"label":"red cube","category":"cube","colour":"red",
"center":[0.4,0.5],"bbox":[0.39,0.49,0.41,0.51],"graspable":true},
{"label":"yellow cap","category":"cap","color":"yellow","centre":[0.6,0.5]}]}
```"""


class FakeEndpoint(BaseHTTPRequestHandler):
    requests = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeEndpoint.requests.append((dict(self.headers), body))
        payload = json.dumps({"choices": [{"message": {"content": REPLY}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


class TryCosmosApiTests(unittest.TestCase):
    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), FakeEndpoint)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.image = Path(self.tmp.name) / "world_camera.png"
        cv2.imwrite(str(self.image), np.full((2160, 3840, 3), 255, np.uint8))
        FakeEndpoint.requests.clear()

    def run_script(self, env_key="nvapi-test"):
        env = dict(os.environ)
        env.pop("NVIDIA_API_KEY", None)
        if env_key:
            env["NVIDIA_API_KEY"] = env_key
        url = f"http://127.0.0.1:{self.server.server_port}/v1/chat/completions"
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.image), "--url", url,
             "--out", str(Path(self.tmp.name) / "out")],
            env=env, capture_output=True, text=True,
        )

    def test_sends_starter_prompt_and_parses_reply(self):
        done = self.run_script()
        self.assertEqual(done.returncode, 0, done.stderr)
        headers, body = FakeEndpoint.requests[0]
        self.assertEqual(headers["Authorization"], "Bearer nvapi-test")
        self.assertEqual(body["model"], "nvidia/cosmos3-nano-reasoner")
        image, text = body["messages"][0]["content"]
        self.assertTrue(image["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertIn("building one cube tower", text["text"])
        self.assertIn("Sending 1920x1080 JPEG", done.stdout)
        self.assertIn("Parsed 1 cubes", done.stdout)
        self.assertIn("'red': 1", done.stdout)
        self.assertTrue((Path(self.tmp.name) / "out" / "cosmos_api_raw.txt").is_file())

    def test_missing_key_stops_before_sending(self):
        done = self.run_script(env_key=None)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("NVIDIA_API_KEY", done.stderr)
        self.assertEqual(FakeEndpoint.requests, [])


if __name__ == "__main__":
    unittest.main()
