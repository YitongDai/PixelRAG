import sys
import os
import asyncio
import time
import glob
import traceback

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
os.makedirs("/dev/shm/pixelrag_render/raw", exist_ok=True)
from pixelrag_render.backends.fast_cdp import render_articles
from pixelrag_render.bench.bench_throughput import prepare_articles
from pixelrag_render.strategies.cdp_phased import CDPPhasedStrategy

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"


async def main():
    try:
        articles = prepare_articles(
            ZIM, 200, seed=42, kiwix_url="http://localhost:9461"
        )
        print(f"{len(articles)} articles", flush=True)

        # Test 1: Raw capture only
        print("=== Raw capture only ===", flush=True)
        s = CDPPhasedStrategy(
            chrome_path=CHROME, n_workers=48, capture_limit=48, fmt="raw"
        )
        await s.setup()
        t0 = time.monotonic()
        caps = await s.capture_articles(articles)
        raw_wall = time.monotonic() - t0
        await s.teardown()
        tiles = sum(len(ac.tiles) for ac in caps if ac)
        for ac in caps or []:
            for tc in ac.tiles if ac else []:
                if tc.raw_file_path:
                    try:
                        os.unlink(tc.raw_file_path)
                    except:
                        pass
        print(
            f"Raw only:      {tiles / raw_wall:.1f} t/s ({tiles} in {raw_wall:.1f}s)",
            flush=True,
        )
        await asyncio.sleep(5)

        # Test 2: fast_cdp (raw + async compression)
        print("=== Raw + async JPEG ===", flush=True)
        r = await render_articles(
            articles=articles,
            output_dir=os.path.expanduser("~/pixelrag/tmp/latency_cmp"),
            chrome_path=CHROME,
            n_workers=48,
            jpeg_quality=85,
            n_compressors=4,
        )
        print(
            f"Capture: {r['capture_tiles_per_s']:.1f} t/s  Total: {r['tiles_per_s']:.1f} t/s",
            flush=True,
        )
        print(
            f"  capture_wall={r['capture_wall_s']:.1f}s  total_wall={r['wall_s']:.1f}s",
            flush=True,
        )
        jpgs = glob.glob(os.path.expanduser("~/pixelrag/tmp/latency_cmp/*/tile_*.jpg"))
        print(f"  JPEG files: {len(jpgs)}", flush=True)
        print(
            f"\nCapture impact: {r['capture_tiles_per_s'] - tiles / raw_wall:+.1f} t/s",
            flush=True,
        )
    except Exception:
        traceback.print_exc()


asyncio.run(main())
