import sys
import os
import asyncio
import traceback

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
sys.stdout.reconfigure(line_buffering=True)
from pixelrag_render.bench.bench_throughput import (
    prepare_articles,
    generate_ground_truth,
    run_and_verify,
    print_latency,
    print_throughput,
)
from pixelrag_render.bench.strategies.cdp_sequential import CDPSequentialStrategy
from pathlib import Path

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
KIWIX = "http://localhost:9454"


async def main():
    articles = prepare_articles(ZIM, 100, seed=42, kiwix_url=KIWIX)
    print(f"{len(articles)} articles (kiwix-serve + image wait)")

    gt_dir = Path(os.path.expanduser("~/pixelrag/tmp/bench_imgwait/gt"))
    gt = await generate_ground_truth(articles, CHROME, gt_dir, seed=42)
    total = sum(len(v) for v in gt.values())
    print(f"GT: {total} tiles")

    # Latency
    print("\n=== LATENCY ===")
    s1 = CDPSequentialStrategy(chrome_path=CHROME, n_workers=1, fmt="raw")
    r1 = await run_and_verify(s1, articles, gt)
    print_latency([r1])

    # Throughput
    print("\n=== THROUGHPUT ===")
    for nw in [32, 48]:
        s = CDPSequentialStrategy(chrome_path=CHROME, n_workers=nw, fmt="raw")
        r = await run_and_verify(s, articles, gt)
        print_throughput([r])


try:
    asyncio.run(main())
except Exception:
    traceback.print_exc()
