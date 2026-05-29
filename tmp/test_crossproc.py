import asyncio, json, subprocess, signal, time, io, tempfile, os, base64
import websockets
import numpy as np
from PIL import Image
from libzim.reader import Archive

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
archive = Archive("/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim")
entry = archive.get_entry_by_path("A/Kinbidhoo")
html = bytes(entry.get_item().content).decode("utf-8")
tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, dir="/home/yichuan/pixelrag/tmp")
tmp.write(html.encode()); tmp.close()

import re
imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)', html)
css_links = re.findall(r'<link[^>]+href=["\']([^"\']+)', html)
print(f"Kinbidhoo: {len(html)//1024}KB, {len(imgs)} imgs, {len(css_links)} CSS")


async def capture_tile(port):
    proc = subprocess.Popen(
        [CHROME, f"--remote-debugging-port={port}", "--headless", "--no-sandbox",
         "--disable-dev-shm-usage", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await asyncio.sleep(3)
    import urllib.request
    data = urllib.request.urlopen(f"http://localhost:{port}/json").read()
    ws = await websockets.connect(json.loads(data)[0]["webSocketDebuggerUrl"],
                                  open_timeout=10, max_size=50 * 1024 * 1024)
    mid = [0]

    async def cmd(method, params=None):
        mid[0] += 1
        msg = {"id": mid[0], "method": method}
        if params:
            msg["params"] = params
        await ws.send(json.dumps(msg))
        while True:
            r = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            if r.get("id") == mid[0]:
                return r

    await cmd("Page.enable")
    await cmd("Emulation.setDeviceMetricsOverride", {
        "width": 875, "height": 8192, "deviceScaleFactor": 1, "mobile": False})
    await cmd("Page.navigate", {"url": "file://" + tmp.name})
    await asyncio.sleep(0.5)

    r = await cmd("Runtime.evaluate",
                  {"expression": "document.documentElement.scrollHeight"})
    h = r["result"]["result"]["value"]

    r = await cmd("Page.captureScreenshot", {
        "directClip": True, "format": "png",
        "clip": {"x": 0, "y": 0, "width": 875, "height": min(1024, h), "scale": 1}})
    tile = base64.b64decode(r["result"]["data"])

    await ws.close()
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    return h, tile


async def main():
    results = []
    for i in range(3):
        h, tile = await capture_tile(9500 + i)
        results.append((h, tile))
        print(f"Process {i}: height={h}px, tile0={len(tile) // 1024}KB")

    print()
    for i in range(3):
        for j in range(i + 1, 3):
            a = np.array(Image.open(io.BytesIO(results[i][1])).convert("RGB"),
                         dtype=np.float32)
            b = np.array(Image.open(io.BytesIO(results[j][1])).convert("RGB"),
                         dtype=np.float32)
            if a.shape != b.shape:
                print(f"proc{i} vs proc{j}: SHAPE MISMATCH {a.shape} vs {b.shape}"
                      f"  heights={results[i][0]},{results[j][0]}")
                continue
            diff = np.abs(a - b)
            mean_d = diff.mean()
            pct = (diff.sum(axis=2) > 0).mean() * 100
            print(f"proc{i} vs proc{j}: mean_diff={mean_d:.2f}  "
                  f"{pct:.1f}% pixels differ  "
                  f"heights={results[i][0]},{results[j][0]}")

    os.unlink(tmp.name)


asyncio.run(main())
