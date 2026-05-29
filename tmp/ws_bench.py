import sys
import os
import time
import glob
import traceback

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))

from pixelrag_render.backends.websocket import render_urls
from pixelrag_render.bench.bench_throughput import prepare_articles

ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
articles = prepare_articles(ZIM, 200, seed=42, kiwix_url="http://localhost:9461")
urls = [a["file"] for a in articles]
print(f"{len(urls)} URLs", flush=True)

try:
    t0 = time.monotonic()
    tile_dirs = render_urls(
        urls, "./tmp/ws_bench", workers=48, quality=85, image_format="jpeg"
    )
    wall = time.monotonic() - t0
    tiles = sum(len(glob.glob(str(d) + "/tile_*")) for d in tile_dirs)
    print(f"websocket.py 48w: {tiles} tiles in {wall:.1f}s = {tiles / wall:.1f} t/s")
except Exception:
    traceback.print_exc()
