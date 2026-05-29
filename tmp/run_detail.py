#!/usr/bin/env python3
"""Detailed timing breakdown of the phased strategy (best config: 80w/48c).

Measures:
- Per-article: nav_ms, sem_wait_ms, shot_ms
- Aggregate: wall, throughput, latency distribution
"""

import sys
import os
import asyncio
import time
import json
import statistics

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
sys.stdout.reconfigure(line_buffering=True)

from pixelrag_render.bench import Bench
from pixelrag_render.bench.bench_throughput import (
    decode_tile,
    verify_tile,
    CORRECT_THRESHOLD,
)
from pixelrag_render.strategies.base import ArticleCapture, TileCapture, article_url
from pixelrag_render.strategies.connection import launch_websocket
from pixelrag_render.strategies.cdp_sequential import TILE_HEIGHT, VIEWPORT_WIDTH


CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
OUT = os.path.expanduser("~/pixelrag/tmp/detail_result.txt")

WAIT_FONTS_IMGS = """new Promise(resolve => {
    const waitEagerImgs = Promise.all(
        Array.from(document.images)
            .filter(i => !i.complete && i.loading !== 'lazy')
            .map(i => new Promise(r => {
                i.addEventListener('load', r, {once: true});
                i.addEventListener('error', r, {once: true});
            }))
    );
    const timeout = new Promise(r => setTimeout(r, 2000));
    Promise.race([
        Promise.all([document.fonts.ready, waitEagerImgs]),
        timeout
    ]).then(() => {
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                document.documentElement.style.scrollBehavior = 'auto';
                const sh = document.documentElement.scrollHeight;
                const body = document.body;
                resolve(body ? Math.min(sh, Math.max(Math.ceil(body.getBoundingClientRect().bottom), 1)) : sh);
            });
        });
    });
})"""


async def main():
    lines = []

    bench = Bench(
        zim_path=ZIM,
        chrome_path=CHROME,
        output_dir=os.path.expanduser("~/pixelrag/tmp/bench_detail"),
        kiwix_url="http://localhost:9461",
    )

    articles = bench.prepare(200, 42)
    gt = await bench.ensure_gt(200, 42)
    print(f"GT ready: {sum(len(v) for v in gt.values())} tiles", flush=True)

    N_WORKERS = 80
    CAPTURE_LIMIT = 48

    # Launch Chrome processes
    print(f"Launching {N_WORKERS} Chrome processes...", flush=True)
    t_setup = time.monotonic()
    conns = []
    for i in range(N_WORKERS):
        c = await launch_websocket(CHROME, 9300 + i)
        await c.cdp("Page.enable")
        await c.cdp(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": VIEWPORT_WIDTH,
                "height": TILE_HEIGHT,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        conns.append(c)
    setup_s = time.monotonic() - t_setup
    print(f"Setup: {setup_s:.1f}s", flush=True)

    os.makedirs("/dev/shm/pixelrag_bench", exist_ok=True)
    sem = asyncio.Semaphore(CAPTURE_LIMIT)

    # Per-article detailed timing
    timings = []  # list of (nav_ms, sem_wait_ms, shot_ms, total_ms)

    queue = asyncio.Queue()
    article_index = {a["path"]: i for i, a in enumerate(articles)}
    for a in articles:
        queue.put_nowait(a)
    all_results = [None] * len(articles)

    async def worker(wi):
        conn = conns[wi]
        while not queue.empty():
            try:
                article = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            t_total = time.monotonic()

            # NAV
            t_nav = time.monotonic()
            try:
                await conn.cdp("Page.navigate", {"url": article_url(article)})
                r = await conn.cdp(
                    "Runtime.evaluate",
                    {
                        "expression": WAIT_FONTS_IMGS,
                        "awaitPromise": True,
                        "returnByValue": True,
                    },
                )
                page_h = max(r["result"]["result"]["value"], 1)
            except Exception:
                page_h = TILE_HEIGHT
            nav_ms = (time.monotonic() - t_nav) * 1000

            # SEM WAIT
            t_sem = time.monotonic()
            await sem.acquire()
            sem_wait_ms = (time.monotonic() - t_sem) * 1000

            # CAPTURE
            t_shot = time.monotonic()
            try:
                clip_h = min(TILE_HEIGHT, page_h)
                raw_path = f"/dev/shm/pixelrag_bench/w{wi}_{id(article)}.raw"
                r = await conn.cdp(
                    "Page.captureScreenshot",
                    {
                        "fromSurface": True,
                        "optimizeForSpeed": True,
                        "rawFilePath": raw_path,
                        "clip": {
                            "x": 0,
                            "y": 0,
                            "width": VIEWPORT_WIDTH,
                            "height": clip_h,
                            "scale": 1,
                        },
                    },
                )
                shot_ms = (time.monotonic() - t_shot) * 1000

                tc = TileCapture(
                    raw_file_path=raw_path,
                    shot_ms=shot_ms,
                    tile_index=0,
                    clip_y=0,
                    clip_h=clip_h,
                )
                ac = ArticleCapture(
                    article_path=article["path"],
                    tiles=[tc],
                    page_height=page_h,
                    n_tiles_expected=1,
                    total_shot_ms=shot_ms,
                    total_nav_ms=nav_ms,
                )
            except Exception as e:
                shot_ms = (time.monotonic() - t_shot) * 1000
                ac = ArticleCapture(article_path=article["path"])
                ac.errors.append(str(e))
            finally:
                sem.release()

            total_ms = (time.monotonic() - t_total) * 1000
            timings.append((nav_ms, sem_wait_ms, shot_ms, total_ms))
            all_results[article_index[article["path"]]] = ac

    # RUN
    print(f"Capturing 200 articles with {N_WORKERS}w/{CAPTURE_LIMIT}c...", flush=True)
    t_wall = time.monotonic()
    await asyncio.gather(*[worker(i) for i in range(N_WORKERS)])
    wall_s = time.monotonic() - t_wall

    # TEARDOWN
    for c in conns:
        await c.close()

    # VERIFY (untimed)
    tiles_ok = 0
    tiles_total = 0
    for ac in all_results:
        if ac is None:
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
    tps = tiles_total / wall_s

    # REPORT
    navs = [t[0] for t in timings]
    sems = [t[1] for t in timings]
    shots = [t[2] for t in timings]
    totals = [t[3] for t in timings]

    def pct(arr, p):
        s = sorted(arr)
        return s[min(int(len(s) * p / 100), len(s) - 1)]

    lines.append(
        f"Phased strategy: {N_WORKERS}w/{CAPTURE_LIMIT}c, 200 articles, raw format"
    )
    lines.append("=" * 60)
    lines.append("")
    lines.append(
        f"Correctness: {tiles_ok}/{tiles_total} = {correct_pct:.1f}%  {'PASS' if correct_pct >= CORRECT_THRESHOLD else 'FAIL'}"
    )
    lines.append(f"Wall time:   {wall_s:.3f}s")
    lines.append(f"Throughput:  {tps:.1f} tiles/s")
    lines.append("")
    lines.append(f"Per-article latency breakdown (n={len(timings)}):")
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
    lines.append(
        f"{'total':>12} {statistics.mean(totals):>6.0f}ms {pct(totals, 50):>6.0f}ms {pct(totals, 95):>6.0f}ms {max(totals):>6.0f}ms"
    )
    lines.append("")
    lines.append("Time attribution:")
    lines.append(f"  nav total:      {sum(navs) / 1000:.1f}s across all articles")
    lines.append(f"  sem_wait total: {sum(sems) / 1000:.1f}s across all articles")
    lines.append(f"  capture total:  {sum(shots) / 1000:.1f}s across all articles")
    lines.append("")
    lines.append("Utilization:")
    lines.append(
        f"  {CAPTURE_LIMIT} capture slots × {wall_s:.2f}s = {CAPTURE_LIMIT * wall_s:.1f} slot-seconds available"
    )
    lines.append(f"  {sum(shots) / 1000:.1f} slot-seconds used for capture")
    lines.append(
        f"  Capture slot utilization: {sum(shots) / 1000 / (CAPTURE_LIMIT * wall_s) * 100:.0f}%"
    )
    lines.append(
        f"  Theoretical max if 100% utilized: {CAPTURE_LIMIT / (statistics.mean(shots) / 1000):.0f} t/s"
    )

    result = "\n".join(lines)
    print(result, flush=True)
    with open(OUT, "w") as f:
        f.write(result + "\n")

    # Also dump raw timings
    with open(os.path.expanduser("~/pixelrag/tmp/detail_timings.jsonl"), "w") as f:
        for nav, sem, shot, total in timings:
            f.write(
                json.dumps(
                    {
                        "nav_ms": nav,
                        "sem_wait_ms": sem,
                        "shot_ms": shot,
                        "total_ms": total,
                    }
                )
                + "\n"
            )


try:
    asyncio.run(main())
except Exception as e:
    with open(OUT, "w") as f:
        f.write(f"CRASH: {e}\n{traceback.format_exc()}")
    traceback.print_exc()
