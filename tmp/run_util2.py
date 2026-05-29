#!/usr/bin/env python3
"""Utilization analysis - single clean run."""

import sys
import os
import asyncio
import time
import statistics

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
sys.stdout.reconfigure(line_buffering=True)

from pixelrag_render.bench.bench_throughput import (
    prepare_articles,
    generate_ground_truth,
    decode_tile,
    verify_tile,
    CORRECT_THRESHOLD,
)
from pixelrag_render.strategies.cdp_phased import CDPPhasedStrategy
from pathlib import Path

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
OUT = os.path.expanduser("~/pixelrag/tmp/util2_result.txt")


async def main():
    articles = prepare_articles(ZIM, 200, seed=42, kiwix_url="http://localhost:9461")
    print(f"{len(articles)} articles", flush=True)

    gt_dir = Path(os.path.expanduser("~/pixelrag/tmp/bench_util2/gt"))
    gt = await generate_ground_truth(articles, CHROME, gt_dir, 42)
    print(f"GT: {sum(len(v) for v in gt.values())} tiles", flush=True)

    s = CDPPhasedStrategy(chrome_path=CHROME, n_workers=80, capture_limit=48, fmt="raw")

    await s.setup()
    print("Setup done", flush=True)

    t0 = time.monotonic()
    captures = await s.capture_articles(articles)
    wall_s = time.monotonic() - t0

    await s.teardown()
    print(f"Capture done in {wall_s:.3f}s", flush=True)

    # Verify
    tiles_ok = tiles_total = 0
    for ac in captures:
        if not ac:
            continue
        gt_tiles = gt.get(ac.article_path, [])
        for tc in ac.tiles:
            tiles_total += 1
            img = decode_tile(tc)
            if img and tc.tile_index < len(gt_tiles):
                ok, _ = verify_tile(img, gt_tiles[tc.tile_index], False)
                if ok:
                    tiles_ok += 1
            if tc.raw_file_path:
                try:
                    os.unlink(tc.raw_file_path)
                except:
                    pass

    correct_pct = tiles_ok / tiles_total * 100 if tiles_total else 0

    # Timing analysis
    navs = [ac.total_nav_ms for ac in captures if ac]
    shots = [ac.total_shot_ms for ac in captures if ac]
    sems = [ac.sem_wait_ms for ac in captures if ac]

    def pct(arr, p):
        s = sorted(arr)
        return s[min(int(len(s) * p / 100), len(s) - 1)]

    cap_slot_s = 48 * wall_s
    cap_used_s = sum(shots) / 1000

    lines = [
        "Phased 80w/48c, 200 articles, raw",
        f"{'=' * 60}",
        f"Correct: {tiles_ok}/{tiles_total} = {correct_pct:.1f}%  {'PASS' if correct_pct >= CORRECT_THRESHOLD else 'FAIL'}",
        f"Wall:    {wall_s:.3f}s",
        f"t/s:     {tiles_total / wall_s:.1f}",
        "",
        "Per-article latency breakdown:",
        f"{'':>12} {'avg':>7} {'p50':>7} {'p95':>7} {'max':>7}",
        f"{'nav':>12} {statistics.mean(navs):>6.0f}ms {pct(navs, 50):>6.0f}ms {pct(navs, 95):>6.0f}ms {max(navs):>6.0f}ms",
        f"{'sem_wait':>12} {statistics.mean(sems):>6.0f}ms {pct(sems, 50):>6.0f}ms {pct(sems, 95):>6.0f}ms {max(sems):>6.0f}ms",
        f"{'capture':>12} {statistics.mean(shots):>6.0f}ms {pct(shots, 50):>6.0f}ms {pct(shots, 95):>6.0f}ms {max(shots):>6.0f}ms",
        "",
        "Utilization:",
        f"  Capture slots: 48 × {wall_s:.2f}s = {cap_slot_s:.1f} slot-s avail",
        f"  Used:          {cap_used_s:.1f} slot-s  ({cap_used_s / cap_slot_s * 100:.0f}%)",
        f"  Theoretical:   {48 / (statistics.mean(shots) / 1000):.0f} t/s (if 100% utilized)",
        "",
        f"Slow navs: >{'.5s'}:{sum(1 for n in navs if n > 500)}  >1s:{sum(1 for n in navs if n > 1000)}  >5s:{sum(1 for n in navs if n > 5000)}",
    ]

    result = "\n".join(lines)
    print(result, flush=True)
    with open(OUT, "w") as f:
        f.write(result + "\n")


try:
    asyncio.run(main())
except Exception as e:
    with open(OUT, "w") as f:
        f.write(f"CRASH: {e}\n{__import__('traceback').format_exc()}")
    __import__("traceback").print_exc()
