from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    # Load the search page
    page.goto("http://localhost:3000")
    page.wait_for_load_state("networkidle")
    page.screenshot(
        path="/home/yichuan/pixelrag/tmp/ss_before_search.png", full_page=True
    )

    # Type and search
    page.fill("input", "Nikola Tesla")
    page.click("button:has-text('Search')")

    # Wait for results to load
    page.wait_for_timeout(8000)
    page.screenshot(
        path="/home/yichuan/pixelrag/tmp/ss_after_search.png", full_page=True
    )

    browser.close()
    print("Screenshots saved")
