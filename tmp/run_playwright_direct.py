#!/usr/bin/env python3
"""
Playwright production tool benchmark - direct async mode.
Uses PlaywrightTool + asyncio.gather for parallel capture.
Bypasses LocalExecutor to use our custom Chrome binary.

Compares with our CDP bench (98 t/s baseline).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

WIKI_SCREENSHOT_SRC = os.path.expanduser("~/pixelrag-src/wiki-screenshot/src")
sys.path.insert(0, WIKI_SCREENSHOT_SRC)

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ARTICLES_FILE = os.path.expanduser("~/pixelrag/tmp/articles_200.json")
OUTPUT_DIR = os.path.expanduser("~/pixelrag/tmp/bench_playwright")


async def run_with_n_workers(articles, n_workers, concurrency_per_worker, label):
    from wiki_screenshot.tools.playwright_tool import PlaywrightTool

    os.makedirs(f"{OUTPUT_DIR}/{label}", exist_ok=True)
    out_dir = f"{OUTPUT_DIR}/{label}"

    # Create N_WORKERS separate PlaywrightTool instances, each in their own asyncio task
    tools = []
    for i in range(n_workers):
        tool = PlaywrightTool(
            width=875,
            max_height=0,
            image_format="png",
            quality=95,
            delay=0,
            device_scale_factor=1,
            enable_gpu=True,
            wait_for_images=False,
            wait_for_fonts=False,
            wait_timeout_ms=500,
            screenshot_timeout_ms=120000,
            extra_browser_args=[
                "--enable-gpu-rasterization",
                "--force-gpu-rasterization",
                "--disable-software-rasterizer",
            ],
            use_cdp_screenshot=True,
            cdp_optimize_for_speed=True,
            cdp_from_surface=True,
            segmented_threshold=20000,
            segment_height=8192,
            segment_max_height=8192,
            segmented_stitch=False,
            segmented_save_tiles=True,
            check_blank_tiles=False,
            tile_manifest_every=1,
            use_page_pool=False,
            executable_path=CHROME,
        )
        tools.append(tool)

    # Setup all browsers
    print(f"  Setting up {n_workers} browsers...", flush=True)
    await asyncio.gather(*[t.setup() for t in tools])

    # Distribute articles across workers
    work = [[] for _ in range(n_workers)]
    for i, art in enumerate(articles):
        work[i % n_workers].append(art)

    total_tiles = [0]
    errors = [0]

    async def worker_fn(worker_idx):
        tool = tools[worker_idx]
        my_articles = work[worker_idx]
        for art in my_articles:
            item = (
                art["id"],
                art["url"],
                f"{out_dir}/art_{art['id']}",
                f"{out_dir}/art_{art['id']}",
            )
            try:
                results = await tool.capture_batch(
                    [item],
                    concurrency=concurrency_per_worker,
                )
                for r in results:
                    if r.status == "success":
                        # Count tiles from saved JSON
                        tiles_json = f"{out_dir}/art_{art['id']}/tiles.json"
                        try:
                            with open(tiles_json) as f:
                                data = json.load(f)
                            total_tiles[0] += len(data.get("tiles", []))
                        except Exception:
                            total_tiles[0] += 1  # fallback: at least 1
                    else:
                        errors[0] += 1
            except Exception:
                errors[0] += 1

    t0 = time.monotonic()
    await asyncio.gather(*[worker_fn(i) for i in range(n_workers)])
    wall_s = time.monotonic() - t0

    # Teardown
    await asyncio.gather(*[t.teardown() for t in tools])

    tiles_per_s = total_tiles[0] / wall_s if wall_s > 0 else 0
    return {
        "label": label,
        "n_workers": n_workers,
        "concurrency": concurrency_per_worker,
        "n_tiles": total_tiles[0],
        "n_errors": errors[0],
        "tiles_per_s": round(tiles_per_s, 1),
        "ms_per_tile": round(wall_s * 1000 / total_tiles[0], 1)
        if total_tiles[0] > 0
        else 0,
        "wall_s": round(wall_s, 1),
    }


async def main():
    with open(ARTICLES_FILE) as f:
        raw = json.load(f)
    articles = [
        {"id": str(i), "url": a["file"], "path": a["path"]} for i, a in enumerate(raw)
    ]
    print(f"Loaded {len(articles)} articles", flush=True)

    configs = [
        # (n_workers, concurrency_per_worker, label)
        (8, 2, "8w_c2"),
        (16, 2, "16w_c2"),
        (32, 1, "32w_c1"),
        (32, 2, "32w_c2"),
    ]

    all_results = []
    log_path = f"{OUTPUT_DIR}/direct_bench_log.txt"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(log_path, "w") as logf:
        for nw, conc, label in configs:
            print(f"\n=== {label} (workers={nw}, concurrency={conc}) ===", flush=True)
            r = await run_with_n_workers(articles, nw, conc, label)
            line = (
                f"  {r['label']:15s} tiles={r['n_tiles']} "
                f"t/s={r['tiles_per_s']:.1f} ms/t={r['ms_per_tile']:.0f} "
                f"err={r['n_errors']} wall={r['wall_s']}s"
            )
            print(line, flush=True)
            logf.write(line + "\n")
            logf.flush()
            all_results.append(r)

    results_path = f"{OUTPUT_DIR}/direct_results.json"
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nResults: {results_path}", flush=True)
    print(f"Log: {log_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
