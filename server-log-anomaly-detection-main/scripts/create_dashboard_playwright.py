import asyncio
from playwright.async_api import async_playwright

KIBANA_URL = "http://localhost:5601"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=100
        )

        page = await browser.new_page(
            viewport={"width": 1600, "height": 1000}
        )

        print("[1] Opening Kibana...")
        await page.goto(
            KIBANA_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        print("[2] Waiting for Kibana frontend...")
        await page.wait_for_timeout(10000)

        print("[3] Opening Lens...")
        await page.goto(
            f"{KIBANA_URL}/app/lens",
            wait_until="domcontentloaded",
            timeout=60000
        )

        print("[4] Lens URL:", page.url)

        # Give Kibana plenty of time to initialize
        print("[5] Waiting for Lens frontend...")
        await page.wait_for_timeout(15000)

        # Check loading screen
        loading = page.locator('[data-test-subj="kbnLoadingMessage"]')

        if await loading.count() > 0:
            try:
                await loading.wait_for(
                    state="hidden",
                    timeout=60000
                )
                print("[6] Kibana loading screen disappeared.")
            except Exception:
                print("[❌] Kibana is still showing Loading Elastic.")

        await page.wait_for_timeout(5000)

        print("[7] Current URL:", page.url)
        print("[8] Page title:", await page.title())

        # Capture the actual page text
        body_text = await page.locator("body").inner_text()

        print("\n========== PAGE TEXT ==========\n")
        print(body_text[:12000])

        # Visible buttons
        buttons = await page.locator("button:visible").all_inner_texts()

        print("\n========== VISIBLE BUTTONS ==========\n")

        for i, button in enumerate(buttons, 1):
            text = button.strip()

            if text:
                print(f"{i}: {text}")

        # data-test-subj elements
        elements = await page.locator(
            "[data-test-subj]:visible"
        ).evaluate_all(
            """els => els.slice(0, 200).map(e => ({
                tag: e.tagName,
                test: e.getAttribute('data-test-subj'),
                text: (e.innerText || '').trim().slice(0, 150)
            }))"""
        )

        print("\n========== DATA-TEST-SUBJ ==========\n")

        for element in elements:
            print(element)

        screenshot_path = "scripts/lens_discovery_2.png"

        await page.screenshot(
            path=screenshot_path,
            full_page=True
        )

        print("\n[9] Screenshot saved:", screenshot_path)

        print("\n[10] Keeping browser open for 30 seconds...")
        await page.wait_for_timeout(30000)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())