#!/usr/bin/env python3
"""Test phased strategy with more articles + fine-tuning."""

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
OUT = os.path.expanduser("~/pixelrag/tmp/phased2_result.txt")


async def main():
    t0 = time.monotonic()
    lines = ["Phased strategy v2: more articles + tuning", "=" * 50]

    configs = [
        # (n_articles, n_workers, capture_limit, label)
        (200, 80, 32, "200art 80w/32c (baseline)"),
        (500, 80, 32, "500art 80w/32c"),
        (500, 80, 24, "500art 80w/24c"),
        (500, 80, 40, "500art 80w/40c"),
        (500, 96, 32, "500art 96w/32c"),
        (500, 64, 24, "500art 64w/24c"),
        (1000, 80, 32, "1000art 80w/32c"),
    ]

    for n_arts, nw, cl, label in configs:
        bench = Bench(
            zim_path=ZIM,
            chrome_path=CHROME,
            output_dir=os.path.expanduser("~/pixelrag/tmp/bench_phased2"),
            kiwix_url="http://localhost:9461",
        )

        s = CDPPhasedStrategy(
            chrome_path=CHROME, n_workers=nw, capture_limit=cl, fmt="raw"
        )

        lines.append(f"\n{label}...")
        print(f"Running {label}...", flush=True)
        try:
            r = await bench.run(s, n_articles=n_arts)
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
