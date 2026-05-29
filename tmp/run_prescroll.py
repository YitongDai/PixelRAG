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


async def main():
    articles = prepare_articles(ZIM, 200, seed=42, kiwix_url="http://localhost:9454")
    print(f"{len(articles)} articles")
    gt_dir = Path(os.path.expanduser("~/pixelrag/tmp/bench_prescroll/gt"))
    gt = await generate_ground_truth(articles, CHROME, gt_dir, seed=42)
    total = sum(len(v) for v in gt.values())
    print(f"GT: {total} tiles")

    print("\n=== LATENCY ===")
    r1 = await run_and_verify(
        CDPSequentialStrategy(chrome_path=CHROME, n_workers=1, fmt="raw"), articles, gt
    )
    print_latency([r1])

    print("\n=== THROUGHPUT ===")
    for nw in [32, 48]:
        r = await run_and_verify(
            CDPSequentialStrategy(chrome_path=CHROME, n_workers=nw, fmt="raw"),
            articles,
            gt,
        )
        print_throughput([r])


try:
    asyncio.run(main())
except:
    traceback.print_exc()
