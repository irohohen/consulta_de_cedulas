
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_content('<input id="test" />')
    try:
        page.locator("#test").fill(None)
    except Exception as e:
        print(f"Caught exception: {e}")
    browser.close()
