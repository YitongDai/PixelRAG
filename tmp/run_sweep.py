#!/usr/bin/env python3
"""Sweep worker counts and servers to find optimal throughput."""

import sys
import os
import asyncio
import traceback
import time

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
sys.stdout.reconfigure(line_buffering=True)

from pixelrag_render.bench import Bench
from pixelrag_render.bench.bench_throughput import format_result_line, CORRECT_THRESHOLD
from pixelrag_render.strategies import CDPSequentialStrategy

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
OUT = os.path.expanduser("~/pixelrag/tmp/sweep_result.txt")

CONFIGS = [
    # (n_workers, kiwix_url, label)
    (48, "http://localhost:9461", "kiwix 48w"),
    (64, "http://localhost:9461", "kiwix 64w"),
    (80, "http://localhost:9461", "kiwix 80w"),
    (96, "http://localhost:9461", "kiwix 96w"),
    (48, "http://localhost:9460", "async 48w"),
    (64, "http://localhost:9460", "async 64w"),
    (80, "http://localhost:9460", "async 80w"),
    (96, "http://localhost:9460", "async 96w"),
]


async def main():
    t0 = time.monotonic()
    lines = ["Worker count × server sweep", "=" * 50]

    for nw, kiwix_url, label in CONFIGS:
        bench = Bench(
            zim_path=ZIM,
            chrome_path=CHROME,
            output_dir=os.path.expanduser("~/pixelrag/tmp/bench_sweep"),
            kiwix_url=kiwix_url,
        )

        strategy = CDPSequentialStrategy(chrome_path=CHROME, n_workers=nw, fmt="raw")

        lines.append(f"\n{label}...")
        print(f"Running {label}...", flush=True)
        try:
            r = await bench.run(strategy)
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
    print(f"\nDone in {time.monotonic() - t0:.0f}s")


try:
    asyncio.run(main())
except Exception as e:
    with open(OUT, "w") as f:
        f.write(f"CRASH: {e}\n{traceback.format_exc()}")
    traceback.print_exc()
