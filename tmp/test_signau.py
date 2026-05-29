import asyncio
import json
import subprocess
import signal
import os
import sys

sys.stdout.reconfigure(line_buffering=True)
import websockets

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
URL = "http://localhost:9454/content/wikipedia_en_all_maxi_2025-08/Signau"


async def get_height(port, wait_ms):
    p = subprocess.Popen(
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

    d = urllib.request.urlopen(f"http://localhost:{port}/json").read()
    ws = await websockets.connect(
        json.loads(d)[0]["webSocketDebuggerUrl"],
        open_timeout=10,
        max_size=50 * 1024 * 1024,
    )
    mid = [0]

    async def c(m, pa=None):
        mid[0] += 1
        msg = {"id": mid[0], "method": m}
        if pa:
            msg["params"] = pa
        await ws.send(json.dumps(msg))
        while True:
            r = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            if r.get("id") == mid[0]:
                return r

    await c("Page.enable")
    await c(
        "Emulation.setDeviceMetricsOverride",
        {"width": 875, "height": 8192, "deviceScaleFactor": 1, "mobile": False},
    )
    await c("Page.navigate", {"url": URL})
    await asyncio.sleep(wait_ms / 1000)
    r = await c(
        "Runtime.evaluate", {"expression": "document.documentElement.scrollHeight"}
    )
    h = r["result"]["result"]["value"]
    # Also check number of loaded images
    r2 = await c(
        "Runtime.evaluate",
        {
            "expression": "Array.from(document.images).filter(i => i.complete).length + '/' + document.images.length"
        },
    )
    imgs = r2["result"]["result"]["value"]
    await ws.close()
    p.send_signal(signal.SIGTERM)
    try:
        p.wait(timeout=5)
    except Exception:
        p.kill()
    return h, imgs


async def main():
    print("Signau via kiwix-serve, height + image loading:")
    for wait in [100, 500, 1000, 2000]:
        heights = []
        for i in range(2):
            h, imgs = await get_height(9700 + i, wait)
            heights.append(h)
            print(f"  wait={wait}ms proc{i}: h={h}  imgs={imgs}")
        stable = len(set(heights)) == 1
        print(f"  → {'STABLE' if stable else 'UNSTABLE'}")
        print()


asyncio.run(main())
