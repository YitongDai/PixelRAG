import sys
import os
import asyncio
import traceback
import time

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
from pixelrag_render.bench.bench_throughput import (
    prepare_articles,
    generate_ground_truth,
    run_and_verify,
    CORRECT_THRESHOLD,
)
from pixelrag_render.bench.strategies.cdp_sequential import CDPSequentialStrategy
from pathlib import Path

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
KIWIX = "http://localhost:9460"
OUT = os.path.expanduser("~/pixelrag/tmp/mt_bench_result.txt")


async def main():
    lines = []
    t0 = time.monotonic()
    articles = prepare_articles(ZIM, 200, seed=42, kiwix_url=KIWIX)
    lines.append(f"{len(articles)} articles (multi-threaded ZIM server)")

    gt_dir = Path(os.path.expanduser("~/pixelrag/tmp/bench_mt_zim/gt"))
    gt = await generate_ground_truth(articles, CHROME, gt_dir, seed=42)
    total = sum(len(v) for v in gt.values())
    lines.append(f"GT: {total} tiles ({time.monotonic() - t0:.0f}s)")

    header = (
        f"{'Config':<25} {'ok/tot':>7} {'%':>6} {'t/s':>7} {'ms/t':>6} {'shot%':>5}"
    )
    lines.append(f"\n{header}")
    lines.append("-" * 60)

    for nw in [1, 32, 48]:
        s = CDPSequentialStrategy(chrome_path=CHROME, n_workers=nw, fmt="raw")
        lines.append(f"Running {s.name}...")
        r = await run_and_verify(s, articles, gt)
        tag = "PASS" if r["correct_pct"] >= CORRECT_THRESHOLD else "FAIL"
        ok_tot = f"{r['tiles_ok']}/{r['tiles_total']}"
        lines.append(
            f"  {r['name']:<23} {ok_tot:>7} {r['correct_pct']:>5.1f}% "
            f"{r['tiles_per_s']:>6.1f} {r['ms_per_tile']:>5.0f} "
            f"{r['shot_pct']:>4.0f}%  {tag}"
        )
        if r["bad_examples"]:
            for ex in r["bad_examples"][:3]:
                lines.append(f"    BAD: {ex}")
        with open(OUT, "w") as f:
            f.write("\n".join(lines) + "\n")

    lines.append(f"\nTotal: {time.monotonic() - t0:.0f}s")
    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")


try:
    asyncio.run(main())
except Exception as e:
    with open(OUT, "w") as f:
        f.write(f"CRASH: {e}\n{traceback.format_exc()}")
