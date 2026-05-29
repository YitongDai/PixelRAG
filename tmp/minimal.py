import asyncio, json, subprocess, os, time, sys
sys.stdout.reconfigure(line_buffering=True)
import websockets

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")

async def test():
    p = subprocess.Popen(
        [CHROME, "--remote-debugging-port=9800", "--headless",
         "--no-sandbox", "--disable-dev-shm-usage", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await asyncio.sleep(4)
    print("chrome up")
    import urllib.request
    d = urllib.request.urlopen("http://localhost:9800/json").read()
    ws = await websockets.connect(
        json.loads(d)[0]["webSocketDebuggerUrl"],
        open_timeout=10, max_size=50*1024*1024)
    print("connected")
    await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
    r = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
    print(f"ok: {r.get('id')}")
    await ws.close()
    p.kill()

asyncio.run(test())
