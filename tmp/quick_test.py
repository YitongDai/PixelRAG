import sys
import os
import asyncio
import traceback

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
OUT = os.path.expanduser("~/pixelrag/tmp/quick_4k.txt")

from pixelrag_render.bench.bench_throughput import (
    prepare_articles,
    generate_ground_truth,
    run_and_verify,
)
from pixelrag_render.bench.strategies.cdp_sequential import CDPSequentialStrategy
from pathlib import Path

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"


async def main():
    lines = []
    arts = prepare_articles(ZIM, 20, seed=42, kiwix_url="http://localhost:9461")
    lines.append(f"{len(arts)} articles")

    gt_dir = Path(os.path.expanduser("~/pixelrag/tmp/bench_4kiwix/gt"))
    gt = await generate_ground_truth(arts, CHROME, gt_dir, 42)
    lines.append(f"GT: {sum(len(v) for v in gt.values())} tiles")

    arts4 = prepare_articles(
        ZIM,
        20,
        seed=42,
        kiwix_url="http://localhost:9461,http://localhost:9462,http://localhost:9463,http://localhost:9464",
    )
    s = CDPSequentialStrategy(chrome_path=CHROME, n_workers=8, fmt="raw")
    r = await run_and_verify(s, arts4, gt)
    tag = "PASS" if r["correct_pct"] >= 99 else "FAIL"
    lines.append(
        f"{r['name']}: {r['tiles_ok']}/{r['tiles_total']} "
        f"{r['correct_pct']:.1f}% {r['tiles_per_s']:.1f}t/s {tag}"
    )
    if r["bad_examples"]:
        for ex in r["bad_examples"][:3]:
            lines.append(f"  BAD: {ex}")

    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")


try:
    asyncio.run(main())
except Exception as e:
    with open(OUT, "w") as f:
        f.write(f"CRASH: {e}\n{traceback.format_exc()}")
