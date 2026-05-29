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
from pixelrag_render.bench.strategies.cdp_pertile_imgwait import (
    CDPPerTileImgWaitStrategy,
)
from pathlib import Path

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
KIWIX = "http://localhost:9470"  # async server
OUT = os.path.expanduser("~/pixelrag/tmp/ptimg_result.txt")


async def main():
    lines = []
    t0 = time.monotonic()

    arts = prepare_articles(ZIM, 200, seed=42, kiwix_url=KIWIX)
    lines.append(f"{len(arts)} articles (async ZIM server)")

    gt_dir = Path(os.path.expanduser("~/pixelrag/tmp/bench_ptimg/gt"))
    gt = await generate_ground_truth(arts, CHROME, gt_dir, 42)
    lines.append(
        f"GT: {sum(len(v) for v in gt.values())} tiles ({time.monotonic() - t0:.0f}s)"
    )

    configs = [
        (
            "seq (eager img wait)",
            CDPSequentialStrategy(chrome_path=CHROME, n_workers=32, fmt="raw"),
        ),
        (
            "ptimg (per-tile wait)",
            CDPPerTileImgWaitStrategy(chrome_path=CHROME, n_workers=32, fmt="raw"),
        ),
        ("seq 48w", CDPSequentialStrategy(chrome_path=CHROME, n_workers=48, fmt="raw")),
        (
            "ptimg 48w",
            CDPPerTileImgWaitStrategy(chrome_path=CHROME, n_workers=48, fmt="raw"),
        ),
    ]

    for label, s in configs:
        lines.append(f"\nRunning {s.name}...")
        try:
            r = await run_and_verify(s, arts, gt)
            tag = "PASS" if r["correct_pct"] >= CORRECT_THRESHOLD else "FAIL"
            ok = f"{r['tiles_ok']}/{r['tiles_total']}"
            lines.append(
                f"  {r['name']:<25} {ok:>7} {r['correct_pct']:>5.1f}% "
                f"{r['tiles_per_s']:>6.1f} {r['ms_per_tile']:>5.0f} "
                f"{r['shot_pct']:>4.0f}%  {tag}"
            )
            if r["bad_examples"]:
                for ex in r["bad_examples"][:3]:
                    lines.append(f"    BAD: {ex}")
        except Exception as e:
            lines.append(f"  {s.name} ERROR: {e}")
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
