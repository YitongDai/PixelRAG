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
    CORRECT_THRESHOLD,
)
from pixelrag_render.bench.strategies.cdp_sequential import CDPSequentialStrategy
from pixelrag_render.bench.strategies.cdp_pipelined_tabs import CDPPipelinedTabsStrategy
from pathlib import Path

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
OUT = os.path.expanduser("~/pixelrag/tmp/pipe2t_bench_result.txt")


async def main():
    lines = []
    articles = prepare_articles(ZIM, 200, seed=42, kiwix_url="http://localhost:9454")
    lines.append(f"{len(articles)} articles (kiwix-serve)")

    gt_dir = Path(os.path.expanduser("~/pixelrag/tmp/bench_pipe2t_v2/gt"))
    gt = await generate_ground_truth(articles, CHROME, gt_dir, seed=42)
    total = sum(len(v) for v in gt.values())
    lines.append(f"GT: {total} tiles")

    configs = [
        CDPSequentialStrategy(chrome_path=CHROME, n_workers=32, fmt="raw"),
        CDPPipelinedTabsStrategy(chrome_path=CHROME, n_workers=32, fmt="raw"),
        CDPSequentialStrategy(chrome_path=CHROME, n_workers=48, fmt="raw"),
        CDPPipelinedTabsStrategy(chrome_path=CHROME, n_workers=48, fmt="raw"),
    ]

    for s in configs:
        lines.append(f"\nRunning {s.name}...")
        try:
            r = await run_and_verify(s, articles, gt)
            tag = "PASS" if r["correct_pct"] >= CORRECT_THRESHOLD else "FAIL"
            lines.append(
                f"  {r['name']:<25} {r['tiles_ok']}/{r['tiles_total']} "
                f"{r['correct_pct']:.1f}%  {r['tiles_per_s']:.1f} t/s  "
                f"shot={r['ms_per_tile']:.0f}ms  {tag}"
            )
            if r["bad_examples"]:
                for ex in r["bad_examples"][:3]:
                    lines.append(f"    BAD: {ex}")
        except Exception as e:
            lines.append(f"  {s.name} ERROR: {e}")
            lines.append(traceback.format_exc())

    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")


try:
    asyncio.run(main())
except Exception as e:
    with open(OUT, "w") as f:
        f.write(f"CRASH: {e}\n{traceback.format_exc()}")
