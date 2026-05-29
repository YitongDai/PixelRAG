#!/usr/bin/env python3
"""Utilization analysis of phased strategy."""

import sys
import os
import asyncio
import time
import statistics

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
sys.stdout.reconfigure(line_buffering=True)

from pixelrag_render.bench import Bench
from pixelrag_render.bench.bench_throughput import run_and_verify
from pixelrag_render.strategies.cdp_phased import CDPPhasedStrategy

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
OUT = os.path.expanduser("~/pixelrag/tmp/util_result.txt")


async def main():
    bench = Bench(
        zim_path=ZIM,
        chrome_path=CHROME,
        output_dir=os.path.expanduser("~/pixelrag/tmp/bench_util"),
        kiwix_url="http://localhost:9461",
    )

    articles = bench.prepare(200, 42)
    gt = await bench.ensure_gt(200, 42)
    print(f"GT ready: {sum(len(v) for v in gt.values())} tiles", flush=True)

    s = CDPPhasedStrategy(chrome_path=CHROME, n_workers=80, capture_limit=48, fmt="raw")

    # Use run_and_verify which handles setup/teardown properly
    r = await run_and_verify(s, articles, gt)

    # Extract per-article timings from the article_captures
    # run_and_verify already tore down, so we need to capture the data
    # before teardown. Let me run manually instead.
    print(
        f"First pass: {r['tiles_per_s']:.1f} t/s, {r['correct_pct']:.1f}%", flush=True
    )

    # Run again with manual control to get per-article data
    s2 = CDPPhasedStrategy(
        chrome_path=CHROME, n_workers=80, capture_limit=48, fmt="raw"
    )
    await s2.setup()
    t0 = time.monotonic()
    captures = await s2.capture_articles(articles)
    wall_s = time.monotonic() - t0
    await s2.teardown()

    # Analyze
    navs = [ac.total_nav_ms for ac in captures if ac]
    shots = [ac.total_shot_ms for ac in captures if ac]
    sems = [ac.sem_wait_ms for ac in captures if ac]
    tiles = sum(len(ac.tiles) for ac in captures if ac)

    def pct(arr, p):
        s = sorted(arr)
        return s[min(int(len(s) * p / 100), len(s) - 1)]

    lines = []
    lines.append(f"Phased strategy: 80w/48c, {len(articles)} articles")
    lines.append("=" * 60)
    lines.append(f"Correctness: {r['correct_pct']:.1f}% (from first pass)")
    lines.append(f"Wall time: {wall_s:.3f}s")
    lines.append(f"Tiles: {tiles}")
    lines.append(f"Throughput: {tiles / wall_s:.1f} t/s")
    lines.append("")
    lines.append(f"Per-article latency (n={len(navs)}):")
    lines.append(f"{'':>12} {'avg':>7} {'p50':>7} {'p95':>7} {'max':>7}")
    lines.append(
        f"{'nav':>12} {statistics.mean(navs):>6.0f}ms {pct(navs, 50):>6.0f}ms {pct(navs, 95):>6.0f}ms {max(navs):>6.0f}ms"
    )
    lines.append(
        f"{'sem_wait':>12} {statistics.mean(sems):>6.0f}ms {pct(sems, 50):>6.0f}ms {pct(sems, 95):>6.0f}ms {max(sems):>6.0f}ms"
    )
    lines.append(
        f"{'capture':>12} {statistics.mean(shots):>6.0f}ms {pct(shots, 50):>6.0f}ms {pct(shots, 95):>6.0f}ms {max(shots):>6.0f}ms"
    )
    lines.append("")
    lines.append("Time attribution (total across all articles):")
    lines.append(f"  nav:      {sum(navs) / 1000:>7.1f}s")
    lines.append(f"  sem_wait: {sum(sems) / 1000:>7.1f}s")
    lines.append(f"  capture:  {sum(shots) / 1000:>7.1f}s")
    lines.append("")
    lines.append("Utilization:")
    cap_slot_s = 48 * wall_s
    cap_used_s = sum(shots) / 1000
    lines.append(
        f"  Capture slots available: 48 × {wall_s:.2f}s = {cap_slot_s:.1f} slot-s"
    )
    lines.append(f"  Capture slots used:      {cap_used_s:.1f} slot-s")
    lines.append(f"  Capture utilization:     {cap_used_s / cap_slot_s * 100:.0f}%")
    lines.append(
        f"  Theoretical max @ 100%:  {48 / (statistics.mean(shots) / 1000):.0f} t/s"
    )
    lines.append("")
    lines.append("Slow nav analysis:")
    lines.append(f"  > 500ms: {sum(1 for n in navs if n > 500)}")
    lines.append(f"  > 1s:    {sum(1 for n in navs if n > 1000)}")
    lines.append(f"  > 5s:    {sum(1 for n in navs if n > 5000)}")

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
