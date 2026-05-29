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

        # 1. Raw CDPPhasedStrategy (baseline, no compression)
        print("=== CDPPhasedStrategy raw 48w (baseline) ===", flush=True)
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
        print(f"  {tiles / raw_wall:.1f} t/s  wall={raw_wall:.2f}s", flush=True)
        await asyncio.sleep(5)

        # 2. fast_cdp (raw + async compression)
        print("\n=== fast_cdp 48w (raw + async JPEG) ===", flush=True)
        for f in glob.glob("/dev/shm/pixelrag_render/raw/*"):
            try:
                os.unlink(f)
            except:
                pass
        r = await render_articles(
            articles=articles,
            output_dir=os.path.expanduser("~/pixelrag/tmp/lat_fc"),
            chrome_path=CHROME,
            n_workers=48,
            jpeg_quality=85,
            n_compressors=4,
        )
        print(
            f"  capture: {r['capture_tiles_per_s']:.1f} t/s  capture_wall={r['capture_wall_s']:.2f}s",
            flush=True,
        )
        print(
            f"  total:   {r['tiles_per_s']:.1f} t/s  total_wall={r['wall_s']:.2f}s",
            flush=True,
        )
        print(
            f"  compress overhead on wall: {r['wall_s'] - r['capture_wall_s']:.2f}s",
            flush=True,
        )

        delta = r["capture_tiles_per_s"] - tiles / raw_wall
        print(f"\n  Capture impact from compression: {delta:+.1f} t/s", flush=True)
    except Exception:
        traceback.print_exc()


asyncio.run(main())
