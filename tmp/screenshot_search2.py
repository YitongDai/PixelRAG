from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    page.goto("http://localhost:3000")
    page.wait_for_load_state("networkidle")

    # Type and search
    page.fill("input", "Nikola Tesla")
    page.click("button:has-text('Search')")

    # Wait for results
    page.wait_for_timeout(10000)
    page.screenshot(path="/home/yichuan/pixelrag/tmp/ss_fixed.png", full_page=True)

    # Also take a viewport-only shot to see above the fold
    page.screenshot(
        path="/home/yichuan/pixelrag/tmp/ss_fixed_viewport.png", full_page=False
    )

    browser.close()
    print("Done")
