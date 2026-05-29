#!/usr/bin/env python3
"""
Simple focused comparison: baseline vs angle+swiftshader.

Reuses the GT from bench_gpu_flags (which has cached GT), uses ports
8500-8600 (far from any other usage), kills any residual Chrome before starting.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../render/src"))
sys.stdout.reconfigure(line_buffering=True)

from pixelrag_render.bench.bench_throughput import (
    Bench,
    format_result_line,
    print_results,
)
from pixelrag_render.strategies.cdp_sequential import CDPSequentialStrategy

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
KIWIX = "http://localhost:9461,http://localhost:9462,http://localhost:9463,http://localhost:9464"
OUTPUT = os.path.expanduser("~/pixelrag/tmp/bench_angle_vs_baseline")

CONFIGS = [
    ("baseline", [], 8500),
    ("angle_swgl", ["--use-gl=angle", "--use-angle=swiftshader"], 8600),
]

N_WORKERS = 32


def kill_ports(base, n):
    for port in range(base, base + n):
        subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
    time.sleep(1)


async def main():
    # Reuse GT from bench_gpu_flags (same ZIM + kiwix + seed=42)
    bench = Bench(
        zim_path=ZIM,
        chrome_path=CHROME,
        output_dir=OUTPUT,
        kiwix_url=KIWIX,
    )

    all_results = []
    for label, extra, base_port in CONFIGS:
        print(
            f"\n--- Cleanup ports {base_port}-{base_port + N_WORKERS - 1} ---",
            flush=True,
        )
        kill_ports(base_port, N_WORKERS)

        s = CDPSequentialStrategy(
            chrome_path=CHROME,
            n_workers=N_WORKERS,
            fmt="raw",
            extra_args=extra if extra else None,
            label=label,
        )
        s._base_port = base_port

        print(f"--- Running {s.name} ---", flush=True)
        try:
            r = await bench.run(s, n_articles=200)
            print(format_result_line(r), flush=True)
            all_results.append(r)
        except Exception:
            print(f"FAILED: {label}", flush=True)
            traceback.print_exc()
        finally:
            print(f"--- Cleanup after {label} ---", flush=True)
            kill_ports(base_port, N_WORKERS)
            await asyncio.sleep(3)

    print("\n" + "=" * 70)
    print("ANGLE vs BASELINE COMPARISON")
    print_results(all_results)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
