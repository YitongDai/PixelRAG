#!/usr/bin/env python3
"""Quick focused comparison: baseline vs angle+swiftshader vs angle+swiftshader+force-rast.

Uses port range 9500-9599 to avoid conflicts with kiwix (9461-9464) and
previous bench sessions (9300-9349).
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
KIWIX = "http://localhost:9461,http://localhost:9462,http://localhost:9463,http://localhost:9464"
OUTPUT = os.path.expanduser("~/pixelrag/tmp/bench_gpu_quick")

# confirmed: angle+swiftshader enables rasterization:enabled_force, gpu_compositing:enabled
CONFIGS = [
    ("baseline", []),  # current: rasterization:disabled_software
    ("angle_swgl", ["--use-gl=angle", "--use-angle=swiftshader"]),
    # what production wiki-screenshot uses (--use-gl=egl silently falls back to angle)
    (
        "egl_flags",
        ["--use-gl=egl", "--enable-features=Vulkan", "--disable-software-rasterizer"],
    ),
]

N_WORKERS = 32
BASE_PORT = 9500  # use 9500-9531 range


async def main():
    bench = Bench(
        zim_path=ZIM,
        chrome_path=CHROME,
        output_dir=OUTPUT,
        kiwix_url=KIWIX,
    )

    all_results = []
    for label, extra in CONFIGS:
        # Use different port base for each config to avoid interference
        port_offset = CONFIGS.index((label, extra)) * 50
        s = CDPSequentialStrategy(
            chrome_path=CHROME,
            n_workers=N_WORKERS,
            fmt="raw",
            extra_args=extra if extra else None,
            label=label,
        )
        # Override base port
        s._base_port = BASE_PORT + port_offset

        print(
            f"\n--- Running {s.name} (ports {s._base_port}-{s._base_port + N_WORKERS - 1}) ---",
            flush=True,
        )
        try:
            r = await bench.run(s, n_articles=200)
            print(format_result_line(r), flush=True)
            all_results.append(r)
        except Exception:
            print(f"FAILED: {label}", flush=True)
            traceback.print_exc()
        finally:
            # Kill any leftover chrome on these ports
            import subprocess

            for port in range(s._base_port, s._base_port + N_WORKERS):
                subprocess.run(
                    ["pkill", "-f", f"remote-debugging-port={port}"],
                    capture_output=True,
                )
            await asyncio.sleep(2)

    print("\n" + "=" * 70)
    print("GPU FLAG QUICK COMPARISON")
    print_results(all_results)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
