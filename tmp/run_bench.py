#!/usr/bin/env python3
"""Compare seq vs ptimg strategies using the clean Bench API."""

import sys
import os
import asyncio
import traceback
import time

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
sys.stdout.reconfigure(line_buffering=True)

from pixelrag_render.bench import Bench
from pixelrag_render.bench.bench_throughput import format_result_line, CORRECT_THRESHOLD
from pixelrag_render.strategies import CDPSequentialStrategy, CDPPerTileImgWaitStrategy

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
KIWIX = "http://localhost:9461"
OUT = os.path.expanduser("~/pixelrag/tmp/bench_result.txt")


async def main():
    t0 = time.monotonic()
    lines = []

    bench = Bench(
        zim_path=ZIM,
        chrome_path=CHROME,
        output_dir=os.path.expanduser("~/pixelrag/tmp/bench_clean"),
        kiwix_url=KIWIX,
        gt_timeout_ms=5000,
    )

    lines.append(f"Bench: {ZIM}")
    lines.append(f"Chrome: {CHROME}")
    lines.append(f"Kiwix: {KIWIX}")

    strategies = [
        CDPSequentialStrategy(chrome_path=CHROME, n_workers=32, fmt="raw"),
        CDPPerTileImgWaitStrategy(chrome_path=CHROME, n_workers=32, fmt="raw"),
        CDPSequentialStrategy(chrome_path=CHROME, n_workers=48, fmt="raw"),
        CDPPerTileImgWaitStrategy(chrome_path=CHROME, n_workers=48, fmt="raw"),
    ]

    for s in strategies:
        label = f"{s.name} ({type(s).__name__})"
        lines.append(f"\nRunning {label}...")
        print(f"Running {label}...", flush=True)
        try:
            r = await bench.run(s)
            line = format_result_line(r)
            lines.append(line)
            print(line, flush=True)
            if r["correct_pct"] < CORRECT_THRESHOLD:
                lines.append("  FAIL!")
                for ex in r.get("bad_examples", [])[:5]:
                    lines.append(f"    {ex}")
        except Exception as e:
            msg = f"  ERROR: {e}"
            lines.append(msg)
            print(msg, flush=True)
            traceback.print_exc()

        with open(OUT, "w") as f:
            f.write("\n".join(lines) + "\n")

    lines.append(f"\nTotal: {time.monotonic() - t0:.0f}s")
    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nDone in {time.monotonic() - t0:.0f}s. Results: {OUT}")


try:
    asyncio.run(main())
except Exception as e:
    with open(OUT, "w") as f:
        f.write(f"CRASH: {e}\n{traceback.format_exc()}")
    traceback.print_exc()
