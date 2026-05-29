import sys
import os
import asyncio
import traceback

sys.path.insert(0, os.path.expanduser("~/pixelrag/render/src"))
sys.stdout.reconfigure(line_buffering=True)
from pixelrag_render.bench.bench_throughput import prepare_articles
from pixelrag_render.bench.strategies.cdp_pipelined_tabs import CDPPipelinedTabsStrategy

CHROME = os.path.expanduser("~/chromium/src/out/Release/chrome")
ZIM = "/mnt/data/yichuan/pixelrag/zim/wikipedia_en_all_maxi_2025-08.zim"
OUT = os.path.expanduser("~/pixelrag/tmp/pipe2t_test_result.txt")


async def test():
    lines = []
    articles = prepare_articles(ZIM, 5, seed=42, kiwix_url="http://localhost:9454")
    lines.append(f"{len(articles)} articles")

    s = CDPPipelinedTabsStrategy(chrome_path=CHROME, n_workers=1, fmt="jpeg")
    lines.append("setup...")
    await s.setup()
    n_pairs = len([p for p in s._tab_pairs if p])
    lines.append(f"tabs: {n_pairs} pairs")

    lines.append("capturing...")
    results = await s.capture_articles(articles)
    lines.append(
        f"results: {len(results)} articles, {sum(len(r.tiles) for r in results)} tiles"
    )
    for r in results:
        lines.append(
            f"  {r.article_path}: {len(r.tiles)} tiles, h={r.page_height}, err={r.errors[:2]}"
        )

    await s.teardown()
    lines.append("done")

    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")


try:
    asyncio.run(test())
except Exception as e:
    with open(OUT, "w") as f:
        f.write(f"CRASH: {e}\n{traceback.format_exc()}")
