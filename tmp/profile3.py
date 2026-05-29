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
            r = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            if r.get("id") == mid[0]:
                return r

    await cmd("Page.enable")
    await cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": 875, "height": 8192, "deviceScaleFactor": 1, "mobile": False},
    )
    os.makedirs("/dev/shm/pixelrag_bench", exist_ok=True)

    lines.append(
        f"{'Article':<20} {'nav':>4} {'fonts':>5} {'pending':>8} {'2rAF':>4} {'shot':>5} {'total':>5}"
    )
    lines.append("-" * 55)

    for name in ARTICLES:
        try:
            t0 = time.monotonic()
            await cmd("Page.navigate", {"url": f"{ZIM}/{name}"})
            t1 = time.monotonic()
            await cmd(
                "Runtime.evaluate",
                {"expression": "document.fonts.ready", "awaitPromise": True},
            )
            t2 = time.monotonic()
            r = await cmd(
                "Runtime.evaluate",
                {
                    "expression": "document.images.length+'/'+Array.from(document.images).filter(i=>!i.complete).length"
                },
            )
            pend = r["result"]["result"]["value"]
            await cmd(
                "Runtime.evaluate",
                {
                    "expression": "new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))",
                    "awaitPromise": True,
                },
            )
            t3 = time.monotonic()
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
            lines.append(
                f"{name:<20} {ms(t0, t1):>4.0f} {ms(t1, t2):>5.0f} {pend:>8} {ms(t2, t3):>4.0f} {ms(t3, t4):>5.0f} {ms(t0, t4):>5.0f}"
            )
        except Exception as e:
            lines.append(f"{name:<20} ERR: {e}")

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
    with open(OUT, "w") as f:
        import traceback

        f.write(f"CRASH: {e}\n{traceback.format_exc()}")
