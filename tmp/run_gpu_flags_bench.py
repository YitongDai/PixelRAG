#!/usr/bin/env python3
"""
Benchmark Chrome GPU flag variants to find fastest rendering path.

Tests:
  - baseline:    current CHROME_ARGS (--enable-gpu-rasterization --force-gpu-rasterization)
  - egl:         + --use-gl=egl --enable-features=Vulkan --disable-software-rasterizer
  - swiftshader: + --use-gl=swiftshader --enable-gpu-rasterization --force-gpu-rasterization
  - no_gpu_flags: plain headless, no GPU rasterization flags (control)

All run at 32 workers, raw format, against kiwix at localhost:9461.
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../render/src"))
sys.stdout.reconfigure(line_buffering=True)

from pixelrag_render.bench import Bench
from pixelrag_render.bench.bench_throughput import print_results, format_result_line
from pixelrag_render.strategies.cdp_sequential import CDPSequentialStrategy

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
KIWIX = "http://localhost:9461"
OUTPUT = os.path.expanduser("~/pixelrag/tmp/bench_gpu_flags")

# Strategy configurations: (label, extra_args_to_add_or_replace)
# Note: CHROME_ARGS in connection.py already has:
#   --no-sandbox --disable-dev-shm-usage
#   --enable-gpu-rasterization --force-gpu-rasterization
#
# Key finding from GPU probing:
# - Without --use-gl=angle --use-angle=swiftshader, Chrome silently falls back to
#   pure software rendering (rasterization: disabled_software, gpu_compositing: disabled_software)
#   even with --enable-gpu-rasterization --force-gpu-rasterization
# - With --use-gl=angle --use-angle=swiftshader, rasterization: enabled_force,
#   gpu_compositing: enabled — SkiaRenderer path is active
CONFIGS = [
    # name, extra_args (appended on top of CHROME_ARGS)
    ("baseline", []),  # current default (software path despite GPU flags)
    ("angle_swgl", ["--use-gl=angle", "--use-angle=swiftshader"]),
    (
        "angle_swgl_notile",
        ["--use-gl=angle", "--use-angle=swiftshader", "--disable-gpu-rasterization"],
    ),  # GPU compositing, but no tiled raster
    (
        "egl+vulkan",
        ["--use-gl=egl", "--enable-features=Vulkan", "--disable-software-rasterizer"],
    ),
]

N_WORKERS = 32


async def main():
    bench = Bench(
        zim_path=ZIM,
        chrome_path=CHROME,
        output_dir=OUTPUT,
        kiwix_url=KIWIX,
    )

    all_results = []
    for label, extra in CONFIGS:
        s = CDPSequentialStrategy(
            chrome_path=CHROME,
            n_workers=N_WORKERS,
            fmt="raw",
            extra_args=extra if extra else None,
            label=label,
        )
        print(f"\n--- Running {s.name} ---", flush=True)
        try:
            r = await bench.run(s, n_articles=200)
            print(format_result_line(r), flush=True)
            all_results.append(r)
        except Exception:
            print(f"FAILED: {label}", flush=True)
            traceback.print_exc()

    print("\n" + "=" * 70)
    print("GPU FLAG BENCHMARK RESULTS")
    print_results(all_results)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
