#!/usr/bin/env python3
"""
Benchmark production PlaywrightTool against our existing kiwix server.

Uses the same 200-article sample as our CDP bench (seed=42) but measures
throughput through the wiki-screenshot PlaywrightTool + LocalExecutor stack.

Kiwix is already running at ports 9461-9464 serving wiki_1..wiki_4.zim
(all maxi ZIM).

Output: t/s, ms/t, n_tiles total.
"""

from __future__ import annotations

import json
import os
import sys
import time

WIKI_SCREENSHOT_SRC = os.path.expanduser("~/pixelrag-src/wiki-screenshot/src")
sys.path.insert(0, WIKI_SCREENSHOT_SRC)

ARTICLES_FILE = os.path.expanduser("~/pixelrag/tmp/articles_200.json")
OUTPUT_DIR = os.path.expanduser("~/pixelrag/tmp/bench_playwright")
CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")

N_ARTICLES = 200
SEED = 42


def main():
    from wiki_screenshot.tools.playwright_tool import PlaywrightTool
    from wiki_screenshot.executors.local import LocalExecutor
    from wiki_screenshot.datasources.base import Article

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Loading articles from {ARTICLES_FILE}...", flush=True)
    with open(ARTICLES_FILE) as f:
        raw_articles = json.load(f)
    print(f"Got {len(raw_articles)} articles.", flush=True)

    articles = [
        Article(id=str(i), title=a["path"], url=a["file"], text=None, html=None)
        for i, a in enumerate(raw_articles)
    ]

    configs = [
        # (num_workers, concurrency, label)
        (32, 2, "32w_c2"),
        (48, 2, "48w_c2"),
        (32, 1, "32w_c1"),
    ]

    log_path = os.path.join(OUTPUT_DIR, "bench_log.txt")
    results_path = os.path.join(OUTPUT_DIR, "bench_results.json")
    all_results = []

    with open(log_path, "w") as logf:
        logf.write(f"Playwright bench, N={N_ARTICLES}, seed={SEED}\n\n")

        for nw, concurrency, label in configs:
            out_dir = os.path.join(OUTPUT_DIR, label)
            os.makedirs(out_dir, exist_ok=True)

            print(
                f"\n--- {label} (workers={nw}, concurrency={concurrency}) ---",
                flush=True,
            )

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
                use_page_pool=True,
                executable_path=CHROME,
            )

            executor = LocalExecutor(
                concurrency=concurrency,
                batch_size=min(200, len(articles)),
                num_workers=nw,
                persistent_workers=True,
                batch_timeout_s=0,
            )

            t0 = time.monotonic()
            results_list = list(
                executor.run(
                    articles=iter(articles),
                    tool=tool,
                    output_dir=out_dir,
                    total=len(articles),
                )
            )
            wall_s = time.monotonic() - t0

            ok = sum(1 for r in results_list if r.status == "success")
            failed = sum(1 for r in results_list if r.status != "success")

            # Count tiles from manifest files
            n_tiles = 0
            for root, dirs, files in os.walk(out_dir):
                for fname in files:
                    if fname == "tiles.json":
                        try:
                            with open(os.path.join(root, fname)) as f:
                                data = json.load(f)
                            n_tiles += len(data.get("tiles", []))
                        except Exception:
                            pass

            tiles_per_s = n_tiles / wall_s if wall_s > 0 else 0
            ms_per_tile = (wall_s * 1000 / n_tiles) if n_tiles > 0 else 0

            line = (
                f"  {label}: ok={ok}/{len(articles)} tiles={n_tiles} "
                f"t/s={tiles_per_s:.1f} ms/t={ms_per_tile:.0f} wall={wall_s:.1f}s"
            )
            print(line, flush=True)
            logf.write(line + "\n")
            logf.flush()

            all_results.append(
                {
                    "label": label,
                    "n_workers": nw,
                    "concurrency": concurrency,
                    "n_ok": ok,
                    "n_failed": failed,
                    "n_tiles": n_tiles,
                    "tiles_per_s": round(tiles_per_s, 2),
                    "ms_per_tile": round(ms_per_tile, 1),
                    "wall_s": round(wall_s, 2),
                }
            )

    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nResults written to {results_path}", flush=True)
    print(f"Log at {log_path}", flush=True)


if __name__ == "__main__":
    main()
