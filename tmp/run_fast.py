#!/usr/bin/env python3
"""Test fast nav + high concurrency to reach 150 t/s."""

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
OUT = os.path.expanduser("~/pixelrag/tmp/fast_result.txt")


async def main():
    t0 = time.monotonic()
    lines = ["Fast nav + high concurrency sweep", "=" * 50]

    bench = Bench(
        zim_path=ZIM,
        chrome_path=CHROME,
        output_dir=os.path.expanduser("~/pixelrag/tmp/bench_fast"),
        kiwix_url="http://localhost:9461",
    )

    configs = [
        # baseline
        (80, 48, 2000, "80w/48c t2000 (baseline)"),
        # faster nav
        (80, 48, 500, "80w/48c t500"),
        (80, 48, 200, "80w/48c t200"),
        (80, 48, 0, "80w/48c t0 (fonts only)"),
        # best timeout + different configs
        (96, 48, 200, "96w/48c t200"),
        (96, 64, 200, "96w/64c t200"),
        (128, 64, 200, "128w/64c t200"),
        (128, 96, 200, "128w/96c t200"),
    ]

    for nw, cl, timeout, label in configs:
        s = CDPPhasedStrategy(
            chrome_path=CHROME,
            n_workers=nw,
            capture_limit=cl,
            fmt="raw",
            nav_timeout_ms=timeout,
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
