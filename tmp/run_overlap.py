#!/usr/bin/env python3
"""Test overlap strategy: 2 tabs per Chrome, nav hidden behind capture."""

import sys
import os
import asyncio
import traceback
import time

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
sys.stdout.reconfigure(line_buffering=True)

from pixelrag_render.bench import Bench
from pixelrag_render.bench.bench_throughput import format_result_line, CORRECT_THRESHOLD
from pixelrag_render.strategies.cdp_phased import CDPPhasedStrategy
from pixelrag_render.strategies.cdp_overlap import CDPOverlapStrategy

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
OUT = os.path.expanduser("~/pixelrag/tmp/overlap_result.txt")


async def main():
    t0 = time.monotonic()
    lines = ["Overlap strategy (2-tab nav/capture overlap)", "=" * 50]

    bench = Bench(
        zim_path=ZIM,
        chrome_path=CHROME,
        output_dir=os.path.expanduser("~/pixelrag/tmp/bench_overlap"),
        kiwix_url="http://localhost:9461",
    )

    strategies = [
        (
            "phased 80w/32c (baseline)",
            CDPPhasedStrategy(
                chrome_path=CHROME, n_workers=80, capture_limit=32, fmt="raw"
            ),
        ),
        (
            "overlap 48w/24c",
            CDPOverlapStrategy(
                chrome_path=CHROME, n_workers=48, capture_limit=24, fmt="raw"
            ),
        ),
        (
            "overlap 48w/32c",
            CDPOverlapStrategy(
                chrome_path=CHROME, n_workers=48, capture_limit=32, fmt="raw"
            ),
        ),
        (
            "overlap 64w/32c",
            CDPOverlapStrategy(
                chrome_path=CHROME, n_workers=64, capture_limit=32, fmt="raw"
            ),
        ),
        (
            "overlap 64w/48c",
            CDPOverlapStrategy(
                chrome_path=CHROME, n_workers=64, capture_limit=48, fmt="raw"
            ),
        ),
        (
            "overlap 80w/32c",
            CDPOverlapStrategy(
                chrome_path=CHROME, n_workers=80, capture_limit=32, fmt="raw"
            ),
        ),
    ]

    for label, s in strategies:
        lines.append(f"\n{label}...")
        print(f"Running {label}...", flush=True)
        try:
            r = await bench.run(s)
            line = format_result_line(r)
            lines.append(line)
            print(line, flush=True)
            if r["correct_pct"] < CORRECT_THRESHOLD:
                for ex in r.get("bad_examples", [])[:3]:
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
    print(f"Done in {time.monotonic() - t0:.0f}s")


try:
    asyncio.run(main())
except Exception as e:
    with open(OUT, "w") as f:
        f.write(f"CRASH: {e}\n{traceback.format_exc()}")
    traceback.print_exc()
