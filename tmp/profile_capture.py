"""Profile each phase of the capture pipeline."""

import sys
import os
import asyncio
import json
import subprocess
import signal
import time

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
sys.stdout.reconfigure(line_buffering=True)
import websockets

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM_URL = "http://localhost:9454/content/wikipedia_en_all_maxi_2025-08"

# Pick articles with varying image counts
ARTICLES = [
    ("Kinbidhoo", "17 imgs"),
    ("United_States", "many imgs"),
    ("Cekov", "few imgs"),
    ("DNA", "some imgs"),
]


async def main():
    proc = subprocess.Popen(
        [
            CHROME,
            "--remote-debugging-port=9700",
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

    data = urllib.request.urlopen("http://localhost:9700/json").read()
    ws = await websockets.connect(
        json.loads(data)[0]["webSocketDebuggerUrl"],
        open_timeout=10,
        max_size=50 * 1024 * 1024,
    )
    mid = [0]

    async def cmd(method, params=None):
        mid[0] += 1
        msg = {"id": mid[0], "method": method}
        if params:
            msg["params"] = params
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

    os.makedirs("/dev/shm/pixelrag_bench", exist_ok=True)

    print(
        f"{'Article':<20} {'nav':>5} {'fonts':>6} {'imgs':>6} {'n_img':>6} "
        f"{'layout':>6} {'scroll':>6} {'shot':>6} {'total':>6}"
    )
    print("-" * 80)

    for name, desc in ARTICLES:
        url = f"{ZIM_URL}/{name}"

        # Phase 1: Navigate
        t0 = time.monotonic()
        await cmd("Page.navigate", {"url": url})
        t_nav = time.monotonic()

        # Phase 2: fonts.ready
        await cmd(
            "Runtime.evaluate",
            {"expression": "document.fonts.ready", "awaitPromise": True},
        )
        t_fonts = time.monotonic()

        # Phase 3: Count + wait images
        r = await cmd(
            "Runtime.evaluate",
            {
                "expression": """new Promise(resolve => {
                const total = document.images.length;
                const pending = Array.from(document.images).filter(i => !i.complete);
                if (pending.length === 0) return resolve(total + '/0');
                Promise.all(pending.map(i => new Promise(r => {
                    i.addEventListener('load', r, {once: true});
                    i.addEventListener('error', r, {once: true});
                }))).then(() => resolve(total + '/' + pending.length));
            })""",
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
        img_info = r["result"]["result"]["value"]
        t_imgs = time.monotonic()

        # Phase 4: Layout (2 rAF + measure height)
        r = await cmd(
            "Runtime.evaluate",
            {
                "expression": """new Promise(resolve => {
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => {
                        resolve(document.documentElement.scrollHeight);
                    });
                });
            })""",
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
        page_h = r["result"]["result"]["value"]
        t_layout = time.monotonic()

        # Phase 5: Scroll to tile 1 (if multi-tile)
        n_tiles = (page_h + 8191) // 8192
        if n_tiles > 1:
            await cmd("Runtime.evaluate", {"expression": "window.scrollTo(0, 8192)"})
            await cmd(
                "Runtime.evaluate",
                {
                    "expression": "new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))",
                    "awaitPromise": True,
                },
            )
        t_scroll = time.monotonic()

        # Phase 6: Screenshot (rawFilePath)
        await cmd(
            "Page.captureScreenshot",
            {
                "rawFilePath": "/dev/shm/pixelrag_bench/profile.raw",
                "fromSurface": True,
                "optimizeForSpeed": True,
                "clip": {
                    "x": 0,
                    "y": 0,
                    "width": 875,
                    "height": min(8192, page_h),
                    "scale": 1,
                },
            },
        )
        t_shot = time.monotonic()

        nav_ms = (t_nav - t0) * 1000
        fonts_ms = (t_fonts - t_nav) * 1000
        imgs_ms = (t_imgs - t_fonts) * 1000
        layout_ms = (t_layout - t_imgs) * 1000
        scroll_ms = (t_scroll - t_layout) * 1000
        shot_ms = (t_shot - t_scroll) * 1000
        total_ms = (t_shot - t0) * 1000

        print(
            f"{name:<20} {nav_ms:>5.0f} {fonts_ms:>5.0f}  {imgs_ms:>5.0f} "
            f"{img_info:>6} {layout_ms:>5.0f}  {scroll_ms:>5.0f}  {shot_ms:>5.0f}  {total_ms:>5.0f}"
        )

    os.unlink("/dev/shm/pixelrag_bench/profile.raw")
    await ws.close()
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=5)


asyncio.run(main())
