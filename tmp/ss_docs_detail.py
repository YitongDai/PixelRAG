from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    page.goto("http://localhost:3000/docs")
    page.wait_for_load_state("networkidle")
    page.screenshot(path="/home/yichuan/pixelrag/tmp/ss_docs_top.png")

    # Scroll down to see Try It section
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(500)
    page.screenshot(path="/home/yichuan/pixelrag/tmp/ss_docs_bottom.png")

    browser.close()
    print("Done")
