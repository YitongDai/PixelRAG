#!/usr/bin/env python3
"""Test phased strategy with work-stealing + higher capture limits."""

import sys
import os
import asyncio
import traceback
import time

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
sys.stdout.reconfigure(line_buffering=True)

from pixelrag_render.bench import Bench
from pixelrag_render.bench.bench_throughput import format_result_line
from pixelrag_render.strategies.cdp_phased import CDPPhasedStrategy

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
OUT = os.path.expanduser("~/pixelrag/tmp/steal_result.txt")


async def main():
    t0 = time.monotonic()
    lines = ["Work-stealing phased + high capture limits", "=" * 50]

    bench = Bench(
        zim_path=ZIM,
        chrome_path=CHROME,
        output_dir=os.path.expanduser("~/pixelrag/tmp/bench_steal"),
        kiwix_url="http://localhost:9461",
    )

    configs = [
        (80, 32, "80w/32c"),
        (80, 48, "80w/48c"),
        (80, 64, "80w/64c"),
        (96, 48, "96w/48c"),
        (96, 64, "96w/64c"),
        (128, 48, "128w/48c"),
        (128, 64, "128w/64c"),
    ]

    for nw, cl, label in configs:
        s = CDPPhasedStrategy(
            chrome_path=CHROME, n_workers=nw, capture_limit=cl, fmt="raw"
        )
        lines.append(f"\n{label}...")
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
