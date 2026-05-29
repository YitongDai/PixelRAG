import sys
import os
import asyncio
import json
import subprocess
import signal
import io
import base64

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
import websockets
import numpy as np
from PIL import Image

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "http://localhost:9454/content/wikipedia_en_all_maxi_2025-08"
OUT = os.path.expanduser("~/pixelrag/tmp/bad_tiles_analysis.txt")


async def render(port, url):
    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={port}",
            "--headless",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    await asyncio.sleep(4)
    import urllib.request

    data = urllib.request.urlopen(f"http://localhost:{port}/json").read()
    ws = await websockets.connect(
        json.loads(data)[0]["webSocketDebuggerUrl"],
        open_timeout=10,
        max_size=50 * 1024 * 1024,
    )
    mid = [0]

    async def cmd(m, p=None):
        mid[0] += 1
        msg = {"id": mid[0], "method": m}
        if p:
            msg["params"] = p
        await ws.send(json.dumps(msg))
        while True:
            r = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            if r.get("id") == mid[0]:
                return r

    await cmd("Page.enable")
    await cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": 875, "height": 8192, "deviceScaleFactor": 1, "mobile": False},
    )
    await cmd("Page.navigate", {"url": url})
    await cmd(
        "Runtime.evaluate",
        {
            "expression": (
                "document.fonts.ready.then(()=>"
                "new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))))"
            ),
            "awaitPromise": True,
        },
    )
    r2 = await cmd(
        "Runtime.evaluate",
        {
            "expression": (
                "document.images.length+'/'+"
                "Array.from(document.images).filter(i=>!i.complete).length"
            )
        },
    )
    imgs = r2["result"]["result"]["value"]
    r = await cmd(
        "Page.captureScreenshot",
        {
            "format": "png",
            "fromSurface": True,
            "optimizeForSpeed": True,
            "clip": {"x": 0, "y": 0, "width": 875, "height": 8192, "scale": 1},
        },
    )
    tile = base64.b64decode(r["result"]["data"])
    await ws.close()
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    return tile, imgs


async def main():
    lines = []
    for name in ["Vanvaas", "Noel_Williams_(Northern_Ireland_politician)"]:
        url = f"{ZIM}/{name}"
        tiles = []
        for i in range(3):
            t, imgs = await render(9700 + i, url)
            tiles.append(t)
            lines.append(f"{name} proc{i}: {len(t) // 1024}KB imgs={imgs}")

        for i in range(3):
            for j in range(i + 1, 3):
                a = np.array(
                    Image.open(io.BytesIO(tiles[i])).convert("RGB"), dtype=np.float32
                )
                b = np.array(
                    Image.open(io.BytesIO(tiles[j])).convert("RGB"), dtype=np.float32
                )
                if a.shape != b.shape:
                    lines.append(f"  {i}v{j}: SHAPE {a.shape}v{b.shape}")
                    continue
                diff = np.abs(a - b)
                lines.append(f"  {i}v{j}: mean={diff.mean():.4f} max={diff.max():.0f}")
        lines.append("")

    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")


try:
    asyncio.run(main())
except Exception as e:
    import traceback

    with open(OUT, "w") as f:
        f.write(f"CRASH: {e}\n{traceback.format_exc()}")
