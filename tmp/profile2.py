import sys
import os
import asyncio
import json
import subprocess
import signal
import time

sys.stdout.reconfigure(line_buffering=True)
import websockets

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM_URL = "http://localhost:9454/content/wikipedia_en_all_maxi_2025-08"

ARTICLES = [
    "Kinbidhoo",
    "DNA",
    "Signau",
    "Cekov",
    "Moon",
    "Mars",
    "Venus",
    "Jupiter",
    "Python_(programming_language)",
    "Nikola_Tesla",
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

    async def cmd(m, p=None):
        mid[0] += 1
        msg = {"id": mid[0], "method": m}
        if p:
            msg["params"] = p
        await ws.send(json.dumps(msg))
        while True:
            r = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            if r.get("id") == mid[0]:
                return r

    await cmd("Page.enable")
    await cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": 875, "height": 8192, "deviceScaleFactor": 1, "mobile": False},
    )

    os.makedirs("/dev/shm/pixelrag_bench", exist_ok=True)

    print(
        f"{'Article':<30} {'nav':>4} {'fonts':>5} {'imgs_pending':>12} "
        f"{'2rAF':>4} {'shot':>5} {'total':>5}"
    )
    print("-" * 75)

    for name in ARTICLES:
        try:
            t0 = time.monotonic()
            await cmd("Page.navigate", {"url": f"{ZIM_URL}/{name}"})
            t_nav = time.monotonic()

            await cmd(
                "Runtime.evaluate",
                {"expression": "document.fonts.ready", "awaitPromise": True},
            )
            t_fonts = time.monotonic()

            r = await cmd(
                "Runtime.evaluate",
                {
                    "expression": "(() => { const t=document.images.length; "
                    "const p=Array.from(document.images).filter(i=>!i.complete).length; "
                    "return t+'/'+p; })()"
                },
            )
            img_info = r["result"]["result"]["value"]

            await cmd(
                "Runtime.evaluate",
                {
                    "expression": "new Promise(r=>requestAnimationFrame("
                    "()=>requestAnimationFrame(r)))",
                    "awaitPromise": True,
                },
            )
            t_raf = time.monotonic()

            await cmd(
                "Page.captureScreenshot",
                {
                    "rawFilePath": "/dev/shm/pixelrag_bench/profile.raw",
                    "fromSurface": True,
                    "optimizeForSpeed": True,
                    "clip": {"x": 0, "y": 0, "width": 875, "height": 8192, "scale": 1},
                },
            )
            t_shot = time.monotonic()

            nav = (t_nav - t0) * 1000
            fonts = (t_fonts - t_nav) * 1000
            raf = (t_raf - t_fonts) * 1000
            shot = (t_shot - t_raf) * 1000
            total = (t_shot - t0) * 1000
            print(
                f"{name:<30} {nav:>4.0f} {fonts:>5.0f} {img_info:>12} "
                f"{raf:>4.0f} {shot:>5.0f} {total:>5.0f}"
            )
        except Exception as e:
            print(f"{name:<30} ERROR: {str(e)[:50]}")

    try:
        os.unlink("/dev/shm/pixelrag_bench/profile.raw")
    except OSError:
        pass
    await ws.close()
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=5)


asyncio.run(main())
