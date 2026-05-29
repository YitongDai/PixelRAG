import sys
import os
import asyncio
import json
import subprocess
import signal
import time

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
import websockets

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "http://localhost:9454/content/wikipedia_en_all_maxi_2025-08"
OUT = os.path.expanduser("~/pixelrag/tmp/profile_result.txt")
ARTICLES = ["Kinbidhoo", "DNA", "Signau", "Cekov", "Moon", "Mars", "Venus"]


async def main():
    lines = []
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
            r = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            if r.get("id") == mid[0]:
                return r

    await cmd("Page.enable")
    await cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": 875, "height": 8192, "deviceScaleFactor": 1, "mobile": False},
    )

    lines.append(
        f"{'Article':<15} {'nav':>4} {'fonts':>5} {'wait_img':>8} {'n_img':>6} {'2rAF':>4} {'shot':>5} {'total':>5}  {'nav+wait':>8}"
    )
    lines.append("-" * 70)

    for name in ARTICLES:
        try:
            t0 = time.monotonic()
            await cmd("Page.navigate", {"url": f"{ZIM}/{name}"})
            t1 = time.monotonic()

            # Wait fonts + images in parallel (like production would)
            r = await cmd(
                "Runtime.evaluate",
                {
                    "expression": """new Promise(resolve => {
                    const waitImgs = Promise.all(
                        Array.from(document.images)
                            .filter(i => !i.complete)
                            .map(i => new Promise(r => {
                                i.addEventListener('load', r, {once: true});
                                i.addEventListener('error', r, {once: true});
                            }))
                    );
                    Promise.all([document.fonts.ready, waitImgs]).then(() => {
                        resolve(document.images.length);
                    });
                })""",
                    "awaitPromise": True,
                    "returnByValue": True,
                },
            )
            n_img = r["result"]["result"]["value"]
            t2 = time.monotonic()

            # 2 rAF
            await cmd(
                "Runtime.evaluate",
                {
                    "expression": "new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))",
                    "awaitPromise": True,
                },
            )
            t3 = time.monotonic()

            # Screenshot
            os.makedirs("/dev/shm/pixelrag_bench", exist_ok=True)
            await cmd(
                "Page.captureScreenshot",
                {
                    "rawFilePath": "/dev/shm/pixelrag_bench/p.raw",
                    "fromSurface": True,
                    "optimizeForSpeed": True,
                    "clip": {"x": 0, "y": 0, "width": 875, "height": 8192, "scale": 1},
                },
            )
            t4 = time.monotonic()

            ms = lambda a, b: (b - a) * 1000
            nav = ms(t0, t1)
            wait = ms(t1, t2)
            raf = ms(t2, t3)
            shot = ms(t3, t4)
            total = ms(t0, t4)
            nav_wait = nav + wait
            lines.append(
                f"{name:<15} {nav:>4.0f} {wait:>5.0f}    {n_img:>6} {raf:>4.0f} {shot:>5.0f} {total:>5.0f}  {nav_wait:>8.0f}"
            )
        except Exception as e:
            lines.append(f"{name:<15} ERR: {e}")

    await ws.close()
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except:
        proc.kill()
    try:
        os.unlink("/dev/shm/pixelrag_bench/p.raw")
    except:
        pass

    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")


try:
    asyncio.run(main())
except Exception as e:
    import traceback

    with open(OUT, "w") as f:
        f.write(f"CRASH: {e}\n{traceback.format_exc()}")
