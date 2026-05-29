#!/usr/bin/env python3
"""Systematic scaling analysis: latency and throughput vs worker count."""

import sys
import os
import asyncio
import traceback
import time
import json

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
sys.stdout.reconfigure(line_buffering=True)

from pixelrag_render.bench import Bench
from pixelrag_render.bench.bench_throughput import run_and_verify
from pixelrag_render.strategies import CDPSequentialStrategy

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
OUT = os.path.expanduser("~/pixelrag/tmp/scaling_result.txt")
JSON_OUT = os.path.expanduser("~/pixelrag/tmp/scaling_data.jsonl")

WORKER_COUNTS = [1, 2, 4, 8, 16, 32, 48, 64, 80, 96]


async def main():
    t0 = time.monotonic()

    bench = Bench(
        zim_path=ZIM,
        chrome_path=CHROME,
        output_dir=os.path.expanduser("~/pixelrag/tmp/bench_scaling"),
        kiwix_url="http://localhost:9461",
    )

    articles = bench.prepare(200, 42)
    gt = await bench.ensure_gt(200, 42)
    gt_tiles = sum(len(v) for v in gt.values())
    print(f"GT: {gt_tiles} tiles", flush=True)

    lines = [
        "Scaling analysis: latency + throughput vs concurrency",
        "=" * 70,
        f"{'workers':>7} {'t/s':>6} {'wall':>6} {'nav_p50':>7} {'nav_p95':>7} "
        f"{'shot_p50':>8} {'shot_p95':>8} {'correct':>7} {'tiles':>5}",
        "-" * 70,
    ]
    print(lines[-3], flush=True)
    print(lines[-1], flush=True)

    for nw in WORKER_COUNTS:
        s = CDPSequentialStrategy(chrome_path=CHROME, n_workers=nw, fmt="raw")
        print(f"Running {nw}w...", flush=True)
        try:
            r = await run_and_verify(s, articles, gt)
        except Exception as e:
            line = f"{nw:>7}  ERROR: {e}"
            lines.append(line)
            print(line, flush=True)
            with open(OUT, "w") as f:
                f.write("\n".join(lines) + "\n")
            continue

        line = (
            f"{nw:>7} {r['tiles_per_s']:>6.1f} {r['wall_s']:>5.2f}s "
            f"{r['nav_avg']:>6.0f}ms {r['nav_p95']:>6.0f}ms "
            f"{r['shot_p50']:>7.0f}ms {r['shot_p95']:>7.0f}ms "
            f"{r['correct_pct']:>6.1f}% {r['tiles_total']:>5}"
        )
        lines.append(line)
        print(line, flush=True)

        with open(JSON_OUT, "a") as f:
            f.write(json.dumps({"workers": nw, **r}, default=str) + "\n")
        with open(OUT, "w") as f:
            f.write("\n".join(lines) + "\n")

    lines.append(f"\nTotal: {time.monotonic() - t0:.0f}s")
    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nDone in {time.monotonic() - t0:.0f}s")


try:
    asyncio.run(main())
except Exception as e:
    with open(OUT, "w") as f:
        f.write(f"CRASH: {e}\n{traceback.format_exc()}")
    traceback.print_exc()
