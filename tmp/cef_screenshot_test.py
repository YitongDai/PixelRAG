#!/usr/bin/env python3
"""
CEF screenshot latency test via cef-capi-py.

CEF OSR (off-screen rendering) mode delivers raw BGRA via on_paint() callback.
This bypasses CDP's ForceRedraw+CopyFromSurface roundtrip entirely.

We test:
1. Single-page load + first paint latency (to estimate per-page overhead)
2. Whether CEF can even initialize on this machine

CEF requires each browser to run in its own process (can't init twice in same
process), so we do a subprocess-per-browser model for parallelism.

IMPORTANT: CEF v131 uses Chromium 131.x base.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import time
import multiprocessing as mp
from multiprocessing import Process, Queue

VENV_SITE = os.path.expanduser("~/pixelrag/.venv/lib/python3.13/site-packages")
if VENV_SITE not in sys.path:
    sys.path.insert(0, VENV_SITE)

KIWIX_URL = "http://localhost:9461/content/wiki_1/Albert_Einstein"
VIEWPORT_W = 875
VIEWPORT_H = 8192  # tall viewport like our CDP bench


def cef_screenshot_worker(url: str, result_queue: Queue, timeout_s: float = 30.0):
    """
    Run in a separate process (CEF can't be init'd twice in same process).
    Loads |url|, captures BGRA from on_paint, reports timing.
    """
    try:
        from cef_capi import (
            base_ctor,
            struct,
            header,
            cef_string_ctor,
            handler,
            size_ctor,
            task_factory,
            RUNTIME_DIR,
        )
        from cef_capi.app_client import client_ctor, app_ctor, settings_main_args_ctor
    except ImportError as e:
        result_queue.put({"error": f"import failed: {e}"})
        return

    t_start = time.monotonic()
    n_paints = 0
    first_paint_t = None
    final_buffer_size = None
    saved_exception = None

    app = app_ctor(single_process=False, disable_gpu=True)

    settings, main_args = settings_main_args_ctor()
    settings.log_severity = struct.LOGSEVERITY_DISABLE
    settings.no_sandbox = 1
    settings.windowless_rendering_enabled = 1

    header.cef_initialize(main_args, settings, app, None)

    saved_browser = None

    @task_factory
    def exit_app():
        if saved_browser is not None:
            bh = ctypes.cast(
                saved_browser.get_host(saved_browser),
                ctypes.POINTER(struct.cef_browser_host_t),
            )
            bh.contents.close_browser(bh, 0)

    client = client_ctor()

    @handler(client)
    def get_render_handler(*_):
        render_handler = base_ctor(struct.cef_render_handler_t)

        @handler(render_handler)
        def on_paint(
            browser: struct.cef_browser_t,
            element_type: int,
            dirty_rects_count: int,
            dirty_rects: struct.cef_rect_t,
            buffer: ctypes.c_void_p,
            width: int,
            height: int,
        ):
            nonlocal n_paints, first_paint_t, final_buffer_size
            if element_type == header.PET_VIEW:
                n_paints += 1
                t_now = time.monotonic()
                if first_paint_t is None:
                    first_paint_t = t_now
                final_buffer_size = width * height * 4

        @handler(render_handler)
        def get_view_rect(browser: struct.cef_browser_t, rect: struct.cef_rect_t):
            rect.x = 0
            rect.y = 0
            rect.width = VIEWPORT_W
            rect.height = VIEWPORT_H
            return 1

        return render_handler

    @handler(client)
    def get_load_handler(*_):
        load_handler = base_ctor(struct.cef_load_handler_t)

        @handler(load_handler)
        def on_loading_state_change(
            browser: struct.cef_browser_t,
            is_loading: int,
            can_go_back: int,
            can_go_forward: int,
        ):
            nonlocal saved_browser
            if not is_loading:
                saved_browser = browser
                # Trigger a paint by calling invalidate on the browser host
                bh = ctypes.cast(
                    browser.get_host(browser), ctypes.POINTER(struct.cef_browser_host_t)
                )
                bh.contents.invalidate(bh, header.PET_VIEW)
                # Wait 500ms for on_paint to fire, then exit
                header.cef_post_delayed_task(header.TID_UI, exit_app(), 500)

        return load_handler

    window_info = struct.cef_window_info_t()
    window_info.windowless_rendering_enabled = 1
    window_info.window_name = cef_string_ctor("cef-bench")

    browser_settings = size_ctor(struct.cef_browser_settings_t)

    header.cef_browser_host_create_browser(
        window_info,
        client,
        cef_string_ctor(url),
        browser_settings,
        None,
        None,
    )

    header.cef_run_message_loop()
    header.cef_shutdown()

    t_end = time.monotonic()

    result_queue.put(
        {
            "error": None,
            "url": url,
            "total_ms": round((t_end - t_start) * 1000, 1),
            "first_paint_ms": round((first_paint_t - t_start) * 1000, 1)
            if first_paint_t
            else None,
            "n_paints": n_paints,
            "buffer_bytes": final_buffer_size,
        }
    )


def run_cef_single(url: str) -> dict:
    """Run one CEF screenshot in a subprocess, return timing dict."""
    q = mp.Queue()
    p = Process(target=cef_screenshot_worker, args=(url, q))
    p.start()
    p.join(timeout=60)
    if p.is_alive():
        p.terminate()
        p.join(timeout=5)
        return {"error": "timeout"}
    if p.exitcode != 0:
        return {"error": f"exit code {p.exitcode}"}
    try:
        return q.get_nowait()
    except Exception as e:
        return {"error": f"no result: {e}"}


def main():
    print("=== CEF screenshot test via cef-capi-py ===", flush=True)
    print(f"URL: {KIWIX_URL}", flush=True)
    print(f"Viewport: {VIEWPORT_W}x{VIEWPORT_H}", flush=True)
    print("", flush=True)

    # Smoke test: one page, measure latency
    print("Test 1: single page latency", flush=True)
    t0 = time.monotonic()
    result = run_cef_single(KIWIX_URL)
    wall = time.monotonic() - t0

    if result.get("error"):
        print(f"  FAILED: {result['error']}", flush=True)
        print("\nCEF path is not viable on this machine.", flush=True)
        return

    print(f"  total_ms    = {result.get('total_ms')} ms", flush=True)
    print(f"  first_paint = {result.get('first_paint_ms')} ms", flush=True)
    print(f"  n_paints    = {result.get('n_paints')}", flush=True)
    print(
        f"  buffer_bytes= {result.get('buffer_bytes')} ({VIEWPORT_W}x{VIEWPORT_H}x4 = {VIEWPORT_W * VIEWPORT_H * 4})",
        flush=True,
    )
    print(
        f"  wall time   = {wall * 1000:.0f} ms (includes subprocess overhead)",
        flush=True,
    )
    print("", flush=True)

    # Test 2: 5 sequential pages to measure steady-state
    urls_to_test = [
        "http://localhost:9461/content/wiki_1/Albert_Einstein",
        "http://localhost:9461/content/wiki_1/Python_(programming_language)",
        "http://localhost:9461/content/wiki_1/United_States",
        "http://localhost:9461/content/wiki_1/World_War_II",
        "http://localhost:9461/content/wiki_1/France",
    ]
    print("Test 2: 5 sequential pages", flush=True)
    latencies = []
    for url in urls_to_test:
        r = run_cef_single(url)
        if r.get("error"):
            print(f"  FAILED {url}: {r['error']}", flush=True)
        else:
            ms = r["total_ms"]
            latencies.append(ms)
            print(f"  {url.split('/')[-1][:30]:30s} {ms:.0f} ms", flush=True)

    if latencies:
        avg = sum(latencies) / len(latencies)
        print(f"\n  avg latency = {avg:.0f} ms/page", flush=True)
        print(f"  → estimated single-process t/s = {1000 / avg:.2f}", flush=True)
        print("", flush=True)
        print(
            "NOTE: CEF parallelism requires N separate processes (1 browser/process).",
            flush=True,
        )
        print(f"  With 32 processes: estimated {32 * 1000 / avg:.1f} t/s", flush=True)

    # Save results
    out_path = os.path.expanduser("~/pixelrag/tmp/cef_test_result.json")
    with open(out_path, "w") as f:
        json.dump(
            {
                "single_page": result,
                "sequential_latencies_ms": latencies,
            },
            f,
            indent=2,
        )
    print(f"\nResults: {out_path}", flush=True)


if __name__ == "__main__":
    main()
