from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    # Home page
    page.goto("http://localhost:3000")
    page.wait_for_load_state("networkidle")
    page.screenshot(path="/home/yichuan/pixelrag/tmp/ss_home.png")

    # Search results
    page.fill("input", "Nikola Tesla")
    page.click("button:has-text('Search')")
    page.wait_for_timeout(10000)
    page.screenshot(path="/home/yichuan/pixelrag/tmp/ss_results.png")

    # API docs
    page.goto("http://localhost:3000/docs")
    page.wait_for_load_state("networkidle")
    page.screenshot(path="/home/yichuan/pixelrag/tmp/ss_docs.png")

    # Status
    page.goto("http://localhost:3000/status")
    page.wait_for_load_state("networkidle")
    page.screenshot(path="/home/yichuan/pixelrag/tmp/ss_status.png")

    browser.close()
    print("Done")
