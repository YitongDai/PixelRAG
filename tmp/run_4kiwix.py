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
KIWIX_4 = "http://localhost:9461,http://localhost:9462,http://localhost:9463,http://localhost:9464"
OUT = os.path.expanduser("~/pixelrag/tmp/bench_4kiwix_result.txt")


async def main():
    lines = []
    t0 = time.monotonic()

    arts_gt = prepare_articles(ZIM, 200, seed=42, kiwix_url="http://localhost:9461")
    gt_dir = Path(os.path.expanduser("~/pixelrag/tmp/bench_4kiwix/gt"))
    gt = await generate_ground_truth(arts_gt, CHROME, gt_dir, 42)
    lines.append(
        f"GT: {sum(len(v) for v in gt.values())} tiles ({time.monotonic() - t0:.0f}s)"
    )

    arts = prepare_articles(ZIM, 200, seed=42, kiwix_url=KIWIX_4)
    lines.append(f"{len(arts)} articles, 4 kiwix instances")

    for nw in [32, 48]:
        for fmt in ["raw", "jpeg"]:
            s = CDPSequentialStrategy(chrome_path=CHROME, n_workers=nw, fmt=fmt)
            lines.append(f"Running {s.name}...")
            r = await run_and_verify(s, arts, gt)
            tag = "PASS" if r["correct_pct"] >= CORRECT_THRESHOLD else "FAIL"
            ok = f"{r['tiles_ok']}/{r['tiles_total']}"
            lines.append(
                f"  {r['name']:<23} {ok:>7} {r['correct_pct']:>5.1f}% "
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
