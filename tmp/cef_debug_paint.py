#!/usr/bin/env python3
"""
Debug: Does CEF on_paint fire for a real Wikipedia page?
Uses the same polling approach as smoke_test.py.
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

URL = "http://localhost:9461/content/wiki_1/Albert_Einstein"
VIEWPORT_W = 875
VIEWPORT_H = 8192


def cef_paint_debug(url: str, result_queue: Queue):
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
        result_queue.put({"error": f"import: {e}"})
        return

    t_start = time.monotonic()
    n_paints = 0
    paint_times = []
    saved_buffer = None
    saved_exception = None
    page_loaded = False

    app = app_ctor(single_process=False, disable_gpu=True)
    settings, main_args = settings_main_args_ctor()
    settings.log_severity = struct.LOGSEVERITY_DISABLE
    settings.no_sandbox = 1
    settings.windowless_rendering_enabled = 1

    header.cef_initialize(main_args, settings, app, None)

    def handle_exception(func):
        def wrapped(*args, **kwargs):
            nonlocal saved_exception
            try:
                return func(*args, **kwargs)
            except Exception as e:
                saved_exception = e

        wrapped.__name__ = func.__name__
        return wrapped

    saved_browser = None

    @task_factory
    def exit_app():
        if saved_browser is not None:
            bh = ctypes.cast(
                saved_browser.get_host(saved_browser),
                ctypes.POINTER(struct.cef_browser_host_t),
            )
            bh.contents.close_browser(bh, 0)

    @task_factory
    @handle_exception
    def check_paint(retry=0):
        nonlocal saved_buffer
        t_check = time.monotonic()
        if saved_buffer is None:
            if retry < 30:  # retry up to 15 seconds
                header.cef_post_delayed_task(
                    header.TID_UI, check_paint(retry=retry + 1), 500
                )
                return
            print(
                f"[check_paint] No paint after {retry} retries ({(t_check - t_start) * 1000:.0f}ms total)",
                flush=True,
            )
            header.cef_post_task(header.TID_UI, exit_app())
            return
        # Got a paint!
        print(
            f"[check_paint] Paint received at retry={retry}, t={int((t_check - t_start) * 1000)}ms, n_paints={n_paints}",
            flush=True,
        )
        header.cef_post_task(header.TID_UI, exit_app())

    client = client_ctor()

    @handler(client)
    def get_render_handler(*_):
        render_handler = base_ctor(struct.cef_render_handler_t)

        @handler(render_handler)
        @handle_exception
        def on_paint(
            browser: struct.cef_browser_t,
            element_type: int,
            dirty_rects_count: int,
            dirty_rects: struct.cef_rect_t,
            buffer: ctypes.c_void_p,
            width: int,
            height: int,
        ):
            nonlocal n_paints, saved_buffer
            t_paint = time.monotonic()
            n_paints += 1
            if element_type == header.PET_VIEW:
                saved_buffer = buffer
                paint_times.append((t_paint - t_start) * 1000)
                print(
                    f"  [on_paint] PET_VIEW #{n_paints} at {(t_paint - t_start) * 1000:.0f}ms size={width}x{height}",
                    flush=True,
                )

        @handler(render_handler)
        @handle_exception
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
        @handle_exception
        def on_loading_state_change(
            browser: struct.cef_browser_t,
            is_loading: int,
            can_go_back: int,
            can_go_forward: int,
        ):
            nonlocal saved_browser, page_loaded
            t_now = time.monotonic()
            print(
                f"  [load] is_loading={is_loading} at {(t_now - t_start) * 1000:.0f}ms",
                flush=True,
            )
            if not is_loading:
                saved_browser = browser
                page_loaded = True
                header.cef_post_delayed_task(header.TID_UI, check_paint(), 500)

        @handler(load_handler)
        @handle_exception
        def on_load_error(
            browser: struct.cef_browser_t,
            frame: struct.cef_frame_t,
            error_code: int,
            error_text,
            failed_url,
        ):
            nonlocal saved_browser
            t_now = time.monotonic()
            print(
                f"  [load_error] code={error_code} at {(t_now - t_start) * 1000:.0f}ms",
                flush=True,
            )
            if frame.is_main(frame):
                saved_browser = browser
                header.cef_post_task(header.TID_UI, exit_app())

        return load_handler

    window_info = struct.cef_window_info_t()
    window_info.windowless_rendering_enabled = 1
    window_info.window_name = cef_string_ctor("cef-debug")

    browser_settings = size_ctor(struct.cef_browser_settings_t)

    header.cef_browser_host_create_browser(
        window_info, client, cef_string_ctor(url), browser_settings, None, None
    )

    header.cef_run_message_loop()
    header.cef_shutdown()

    t_end = time.monotonic()
    result = {
        "total_ms": round((t_end - t_start) * 1000, 1),
        "n_paints": n_paints,
        "paint_times_ms": paint_times,
        "page_loaded": page_loaded,
        "error": str(saved_exception) if saved_exception else None,
    }
    print(f"RESULT: {result}", flush=True)
    result_queue.put(result)


def main():
    q = mp.Queue()
    p = Process(target=cef_paint_debug, args=(URL, q))
    p.start()
    p.join(timeout=120)
    if p.is_alive():
        p.terminate()
        p.join(5)
        print("TIMEOUT")
        return
    try:
        r = q.get_nowait()
        print(f"Final: {json.dumps(r, indent=2)}")
    except Exception as e:
        print(f"No result: {e}")


if __name__ == "__main__":
    main()
