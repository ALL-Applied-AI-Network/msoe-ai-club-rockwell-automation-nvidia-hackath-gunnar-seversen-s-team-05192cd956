"""Send the starter's cube-detection prompt to a hosted Cosmos reasoner.

A no-GPU smoke test of perception: does the hosted cosmos3-nano-reasoner
answer perceive.py's STACK_PROMPT with parseable cube detections? It reuses
the starter's prompt and JSON parsing unchanged; perceive.py is not modified.

    export NVIDIA_API_KEY=nvapi-...      # from build.nvidia.com; never commit it
    fanuc_er4ia_sim/.venv/bin/python harness/try_cosmos_api.py IMAGE.png

The hosted endpoint is not confirmed to serve the same weights or image
resolution as the local Cosmos3-Nano run, so treat results as indicative only.
Inputs sent to build.nvidia.com are logged by NVIDIA: send simulator images,
not photos of people or confidential plant equipment.
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fanuc_er4ia_sim"))
from perceive import STACK_PROMPT, canonicalise, parse_json  # noqa: E402

DEFAULT_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_MODEL = "nvidia/cosmos3-nano-reasoner"


def image_data_url(path, max_side):
    """JPEG data URL, downscaled so the request stays small."""
    img = cv2.imread(str(path))
    if img is None:
        raise SystemExit(f"Cannot read image: {path}")
    scale = min(1.0, max_side / max(img.shape[:2]))
    if scale < 1.0:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise SystemExit("JPEG encoding failed")
    return "data:image/jpeg;base64," + base64.b64encode(jpeg.tobytes()).decode(), img.shape[:2]


def build_request(model, data_url, prompt, max_tokens):
    # Same order as perceive.ask: image first, then the text prompt.
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }


def post(url, key, payload, timeout):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"HTTP {exc.code} from {url}: {exc.read()[:500].decode(errors='replace')}")


def summarise(reply_text):
    parsed = parse_json(reply_text)
    if parsed is None:
        return None, []
    parsed = canonicalise(parsed)
    cubes = [o for o in parsed.get("objects", []) if o.get("category") == "cube"]
    return parsed, cubes


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("image", help="table-camera image, e.g. a run's world_camera.png")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--max-side", type=int, default=1920, help="downscale longest side to this")
    ap.add_argument("--max-tokens", type=int, default=3500, help="perceive.py uses 3500")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--out", help="save the raw reply and parsed JSON here")
    a = ap.parse_args()
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        raise SystemExit("Set NVIDIA_API_KEY (create one at build.nvidia.com)")
    data_url, (h, w) = image_data_url(a.image, a.max_side)
    print(f"Sending {w}x{h} JPEG ({len(data_url) / 1e6:.1f} MB as base64) to {a.model}")
    response = post(a.url, key, build_request(a.model, data_url, STACK_PROMPT, a.max_tokens), a.timeout)
    text = response["choices"][0]["message"]["content"] or ""
    parsed, cubes = summarise(text)
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "cosmos_api_raw.txt").write_text(text)
        (out / "cosmos_api_response.json").write_text(json.dumps(response, indent=2))
    if parsed is None:
        print("Reply was not parseable JSON. Raw reply:\n" + text[:1500])
        sys.exit(1)
    print(f"Parsed {len(cubes)} cubes:")
    for o in cubes:
        print(f"  {o.get('colour', '?'):8s} center={o.get('center')} bbox={o.get('bbox')}")
    counts = {c: sum(o.get("colour") == c for o in cubes) for c in ("yellow", "blue", "red")}
    print(f"Colour counts {counts}; the stack task needs 2 of each.")


if __name__ == "__main__":
    main()
