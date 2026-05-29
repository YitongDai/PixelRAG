#!/usr/bin/env python3
"""Test phased strategy: more workers, limited concurrent captures."""

import sys
import os
import asyncio
import traceback
import time

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
sys.stdout.reconfigure(line_buffering=True)

from pixelrag_render.bench import Bench
from pixelrag_render.bench.bench_throughput import format_result_line
from pixelrag_render.strategies import CDPSequentialStrategy
from pixelrag_render.strategies.cdp_phased import CDPPhasedStrategy

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
OUT = os.path.expanduser("~/pixelrag/tmp/phased_result.txt")


async def main():
    t0 = time.monotonic()
    lines = ["Phased strategy sweep", "=" * 50]

    bench = Bench(
        zim_path=ZIM,
        chrome_path=CHROME,
        output_dir=os.path.expanduser("~/pixelrag/tmp/bench_phased"),
        kiwix_url="http://localhost:9461",
    )

    # Baseline
    strategies = [
        (
            "baseline",
            CDPSequentialStrategy(chrome_path=CHROME, n_workers=64, fmt="raw"),
        ),
    ]
    # Phased: vary total workers and capture limit
    for nw in [64, 80, 96]:
        for cl in [24, 32, 48]:
            if cl >= nw:
                continue
            strategies.append(
                (
                    f"phased {nw}w/{cl}c",
                    CDPPhasedStrategy(
                        chrome_path=CHROME, n_workers=nw, capture_limit=cl, fmt="raw"
                    ),
                )
            )

    for label, s in strategies:
        lines.append(f"\n{label} ({s.name})...")
        print(f"Running {label}...", flush=True)
        try:
            r = await bench.run(s)
            line = format_result_line(r)
            lines.append(line)
            print(line, flush=True)
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
    print(f"Done in {time.monotonic() - t0:.0f}s")


try:
    asyncio.run(main())
except Exception as e:
    with open(OUT, "w") as f:
        f.write(f"CRASH: {e}\n{traceback.format_exc()}")
    traceback.print_exc()
