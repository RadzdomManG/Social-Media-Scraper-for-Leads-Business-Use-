from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from typing import Any, Iterable

from config import (
    CAPTCHA_TEXT_PATTERNS,
    DEFAULT_VIEWPORT,
    GOOGLE_MAPS_URL,
    LISTING_CARD_SELECTORS,
    RESULTS_PANEL_SELECTORS,
    SEARCH_INPUT_SELECTOR,
    USER_AGENTS,
)
from utils import CaptchaDetectedError, clean_extracted_text, random_delay


STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(Notification, 'permission', {get: () => 'default'});
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery.call(window.navigator.permissions, parameters)
);
"""


class BaseMapsBrowser(ABC):
    backend = "base"

    def __init__(
        self,
        visible: bool,
        language: str,
        delay_min: float,
        delay_max: float,
        logger: Any,
    ) -> None:
        self.visible = visible
        self.language = language
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.logger = logger
        self.user_agent = random.choice(USER_AGENTS)

    async def wait_random(self, minimum: float | None = None, maximum: float | None = None) -> None:
        await random_delay(minimum or self.delay_min, maximum or self.delay_max)

    async def detect_captcha(self) -> bool:
        body_text = (await self.page_text()).casefold()
        return any(token in body_text for token in CAPTCHA_TEXT_PATTERNS)

    async def handle_captcha_if_needed(self) -> None:
        if not await self.detect_captcha():
            return
        if self.visible:
            self.logger.warning("CAPTCHA or unusual traffic page detected. Waiting for manual solve.")
            await asyncio.to_thread(
                input,
                "CAPTCHA detected in the browser. Solve it manually, then press Enter to continue...",
            )
            return
        raise CaptchaDetectedError(
            "CAPTCHA or unusual traffic page detected in headless mode."
        )

    async def open_maps_home(self) -> None:
        await self.goto(GOOGLE_MAPS_URL)
        await self.wait_for_selector([SEARCH_INPUT_SELECTOR], timeout=20000)
        await self.handle_captcha_if_needed()

    async def submit_search(self, search_text: str) -> None:
        await self.click_selector([SEARCH_INPUT_SELECTOR])
        await self.type_text(SEARCH_INPUT_SELECTOR, search_text, clear=True)
        await self.press_enter(SEARCH_INPUT_SELECTOR)
        try:
            await self.wait_for_results_panel()
            return
        except Exception as original_error:
            self.logger.warning("Initial results-panel detection failed, trying fallback readiness checks.")
            for _ in range(20):
                await self.handle_captcha_if_needed()
                current_url = await self.current_url()
                if "/maps/search/" in current_url or "/maps/place/" in current_url:
                    return
                hrefs = await self.list_attributes(LISTING_CARD_SELECTORS, "href")
                if any("/maps/place/" in href for href in hrefs):
                    return
                page_text = await self.page_text()
                if "results for" in page_text.casefold() or "results" in page_text.casefold():
                    return
                await self.wait_random(0.8, 1.4)
            raise original_error

    async def wait_for_results_panel(self) -> None:
        try:
            await self.wait_for_selector(RESULTS_PANEL_SELECTORS, timeout=30000)
        except Exception:
            current_url = await self.current_url()
            page_text = await self.page_text()
            if "/maps/search/" in current_url:
                for _ in range(5):
                    hrefs = await self.list_attributes(LISTING_CARD_SELECTORS, "href")
                    if any("/maps/place/" in href for href in hrefs):
                        await self.handle_captcha_if_needed()
                        await self.wait_random(1.0, 2.0)
                        return
                    await self.wait_random(1.0, 2.0)
            if "results" in page_text.casefold():
                await self.handle_captcha_if_needed()
                await self.wait_random(1.0, 2.0)
                return
            raise
        await self.handle_captcha_if_needed()
        await self.wait_random(1.0, 2.5)

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def goto(self, url: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def go_back(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def current_url(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def page_text(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def wait_for_selector(self, selectors: Iterable[str], timeout: int = 10000) -> str:
        raise NotImplementedError

    @abstractmethod
    async def selector_exists(self, selector: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def click_selector(self, selectors: Iterable[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def type_text(self, selector: str, value: str, clear: bool = True) -> None:
        raise NotImplementedError

    @abstractmethod
    async def press_enter(self, selector: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def text_content(self, selectors: Iterable[str]) -> str:
        raise NotImplementedError

    @abstractmethod
    async def attribute_value(self, selectors: Iterable[str], attribute: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def list_attributes(self, selectors: Iterable[str], attribute: str) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def all_text_contents(self, selector: str) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def scroll_selector(self, selector: str, amount: int) -> None:
        raise NotImplementedError

    @abstractmethod
    async def scroll_page(self, amount: int) -> None:
        raise NotImplementedError

    async def resolve_first_visible_selector(self, selectors: Iterable[str]) -> str:
        for selector in selectors:
            if await self.selector_exists(selector):
                return selector
        raise TimeoutError("Could not resolve a visible selector from the provided list.")


class PlaywrightMapsBrowser(BaseMapsBrowser):
    backend = "playwright"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._pw = None
        self.browser = None
        self.context = None
        self.page = None

    def _locator(self, selector: str):
        if selector.startswith("xpath="):
            return self.page.locator(selector)
        if selector.startswith("//"):
            return self.page.locator(f"xpath={selector}")
        return self.page.locator(selector)

    async def start(self) -> None:
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()

        async def _route_handler(route) -> None:
            if route.request.resource_type in {"image", "media", "font"}:
                await route.abort()
            else:
                await route.continue_()

        self.browser = await self._pw.chromium.launch(
            headless=not self.visible,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--disable-notifications",
                "--disable-popup-blocking",
                "--no-default-browser-check",
                "--no-first-run",
            ],
        )
        self.context = await self.browser.new_context(
            viewport=DEFAULT_VIEWPORT,
            user_agent=self.user_agent,
            locale=self.language,
            timezone_id="Asia/Manila",
        )
        await self.context.add_init_script(STEALTH_SCRIPT)
        await self.context.route("**/*", _route_handler)
        self.page = await self.context.new_page()
        self.page.set_default_timeout(15000)

    async def close(self) -> None:
        if self.context is not None:
            await self.context.close()
        if self.browser is not None:
            await self.browser.close()
        if self._pw is not None:
            await self._pw.stop()

    async def goto(self, url: str) -> None:
        await self.page.goto(url, wait_until="domcontentloaded")
        await self.wait_random(0.2, 0.45)

    async def go_back(self) -> None:
        await self.page.go_back(wait_until="domcontentloaded")
        await self.wait_random(0.15, 0.35)

    async def current_url(self) -> str:
        return self.page.url

    async def page_text(self) -> str:
        try:
            return clean_extracted_text(await self.page.locator("body").inner_text())
        except Exception:  # noqa: BLE001
            return ""

    async def wait_for_selector(self, selectors: Iterable[str], timeout: int = 10000) -> str:
        last_error: Exception | None = None
        for selector in selectors:
            try:
                locator = self._locator(selector).first
                await locator.wait_for(state="visible", timeout=timeout)
                return selector
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        if last_error:
            raise last_error
        raise TimeoutError("No selector provided")

    async def selector_exists(self, selector: str) -> bool:
        try:
            return await self._locator(selector).count() > 0
        except Exception:  # noqa: BLE001
            return False

    async def click_selector(self, selectors: Iterable[str]) -> None:
        selector = await self.wait_for_selector(selectors, timeout=10000)
        locator = self._locator(selector).first
        box = await locator.bounding_box()
        if box:
            start_x = random.randint(50, 250)
            start_y = random.randint(50, 250)
            end_x = box["x"] + box["width"] / 2 + random.uniform(-6, 6)
            end_y = box["y"] + box["height"] / 2 + random.uniform(-6, 6)
            await self.page.mouse.move(start_x, start_y)
            await self.page.mouse.move(end_x, end_y, steps=random.randint(12, 24))
        await locator.click(delay=random.randint(40, 140))
        await self.wait_random(0.08, 0.2)

    async def type_text(self, selector: str, value: str, clear: bool = True) -> None:
        locator = self._locator(selector).first
        await locator.wait_for(state="visible", timeout=10000)
        await locator.click()
        if clear:
            await locator.fill("")
        for char in value:
            await locator.type(char, delay=random.randint(10, 30))
        await self.wait_random(0.05, 0.12)

    async def press_enter(self, selector: str) -> None:
        await self._locator(selector).first.press("Enter")
        await self.wait_random(0.15, 0.3)

    async def text_content(self, selectors: Iterable[str]) -> str:
        for selector in selectors:
            try:
                locator = self._locator(selector).first
                if await locator.count() > 0:
                    value = await locator.inner_text()
                    if value and value.strip():
                        return clean_extracted_text(value)
            except Exception:  # noqa: BLE001
                continue
        return ""

    async def attribute_value(self, selectors: Iterable[str], attribute: str) -> str:
        for selector in selectors:
            try:
                locator = self._locator(selector).first
                if await locator.count() > 0:
                    value = await locator.get_attribute(attribute)
                    if value:
                        return value.strip()
            except Exception:  # noqa: BLE001
                continue
        return ""

    async def list_attributes(self, selectors: Iterable[str], attribute: str) -> list[str]:
        seen: list[str] = []
        for selector in selectors:
            try:
                locator = self._locator(selector)
                count = await locator.count()
                for index in range(count):
                    value = await locator.nth(index).get_attribute(attribute)
                    if value:
                        seen.append(value.strip())
            except Exception:  # noqa: BLE001
                continue
        return seen

    async def all_text_contents(self, selector: str) -> list[str]:
        try:
            locator = self._locator(selector)
            count = await locator.count()
            values: list[str] = []
            for index in range(count):
                text = await locator.nth(index).inner_text()
                if text.strip():
                    values.append(clean_extracted_text(text))
            return values
        except Exception:  # noqa: BLE001
            return []

    async def scroll_selector(self, selector: str, amount: int) -> None:
        await self._locator(selector).evaluate("(el, delta) => el.scrollBy(0, delta)", amount)
        await self.wait_random(0.08, 0.18)

    async def scroll_page(self, amount: int) -> None:
        await self.page.mouse.wheel(0, amount)
        await self.wait_random(0.08, 0.18)


class SeleniumMapsBrowser(BaseMapsBrowser):
    backend = "selenium"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.driver = None

    async def start(self) -> None:
        import undetected_chromedriver as uc
        from selenium.webdriver.chrome.options import Options

        options = Options()
        options.add_argument(f"--lang={self.language}")
        options.add_argument(f"--user-agent={self.user_agent}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-notifications")
        options.add_argument("--window-size=1366,768")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_experimental_option(
            "prefs",
            {
                "profile.managed_default_content_settings.images": 2,
                "profile.default_content_setting_values.notifications": 2,
            },
        )
        self.driver = await asyncio.to_thread(
            uc.Chrome,
            options=options,
            headless=not self.visible,
            use_subprocess=True,
        )
        await asyncio.to_thread(self.driver.set_page_load_timeout, 45)
        await asyncio.to_thread(self.driver.execute_script, STEALTH_SCRIPT)

    async def close(self) -> None:
        if self.driver is not None:
            await asyncio.to_thread(self.driver.quit)

    async def goto(self, url: str) -> None:
        await asyncio.to_thread(self.driver.get, url)
        await self.wait_random(0.2, 0.45)

    async def go_back(self) -> None:
        await asyncio.to_thread(self.driver.back)
        await self.wait_random(0.15, 0.35)

    async def current_url(self) -> str:
        return await asyncio.to_thread(lambda: self.driver.current_url)

    async def page_text(self) -> str:
        try:
            return clean_extracted_text(
                await asyncio.to_thread(lambda: self.driver.find_element("tag name", "body").text)
            )
        except Exception:  # noqa: BLE001
            return ""

    def _find_elements(self, selector: str):
        from selenium.webdriver.common.by import By

        if selector.startswith("xpath="):
            return self.driver.find_elements(By.XPATH, selector.replace("xpath=", "", 1))
        if selector.startswith("//"):
            return self.driver.find_elements(By.XPATH, selector)
        return self.driver.find_elements(By.CSS_SELECTOR, selector)

    async def wait_for_selector(self, selectors: Iterable[str], timeout: int = 10000) -> str:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        last_error: Exception | None = None
        for selector in selectors:
            try:
                by = By.XPATH if selector.startswith(("xpath=", "//")) else By.CSS_SELECTOR
                value = selector.replace("xpath=", "", 1) if selector.startswith("xpath=") else selector
                await asyncio.to_thread(
                    WebDriverWait(self.driver, timeout / 1000).until,
                    EC.visibility_of_element_located((by, value)),
                )
                return selector
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        if last_error:
            raise last_error
        raise TimeoutError("No selector provided")

    async def selector_exists(self, selector: str) -> bool:
        try:
            elements = await asyncio.to_thread(self._find_elements, selector)
            return len(elements) > 0
        except Exception:  # noqa: BLE001
            return False

    async def click_selector(self, selectors: Iterable[str]) -> None:
        from selenium.webdriver import ActionChains

        selector = await self.wait_for_selector(selectors, timeout=10000)
        elements = await asyncio.to_thread(self._find_elements, selector)
        element = elements[0]

        def _click() -> None:
            actions = ActionChains(self.driver)
            actions.move_to_element_with_offset(
                element,
                random.randint(1, 8),
                random.randint(1, 8),
            ).pause(random.uniform(0.1, 0.3)).click().perform()

        await asyncio.to_thread(_click)
        await self.wait_random(0.3, 0.8)

    async def type_text(self, selector: str, value: str, clear: bool = True) -> None:
        from selenium.webdriver.common.keys import Keys

        elements = await asyncio.to_thread(self._find_elements, selector)
        if not elements:
            raise RuntimeError(f"Selector not found: {selector}")
        element = elements[0]
        await asyncio.to_thread(element.click)
        if clear:
            await asyncio.to_thread(element.clear)
            await asyncio.to_thread(element.send_keys, Keys.CONTROL, "a")
            await asyncio.to_thread(element.send_keys, Keys.DELETE)
        for char in value:
            await asyncio.to_thread(element.send_keys, char)
            await asyncio.sleep(random.uniform(0.04, 0.11))
        await self.wait_random(0.2, 0.5)

    async def press_enter(self, selector: str) -> None:
        from selenium.webdriver.common.keys import Keys

        elements = await asyncio.to_thread(self._find_elements, selector)
        if not elements:
            raise RuntimeError(f"Selector not found: {selector}")
        await asyncio.to_thread(elements[0].send_keys, Keys.ENTER)
        await self.wait_random(0.8, 1.4)

    async def text_content(self, selectors: Iterable[str]) -> str:
        for selector in selectors:
            try:
                elements = await asyncio.to_thread(self._find_elements, selector)
                if elements:
                    text = await asyncio.to_thread(lambda: elements[0].text)
                    if text and text.strip():
                        return clean_extracted_text(text)
            except Exception:  # noqa: BLE001
                continue
        return ""

    async def attribute_value(self, selectors: Iterable[str], attribute: str) -> str:
        for selector in selectors:
            try:
                elements = await asyncio.to_thread(self._find_elements, selector)
                if elements:
                    value = await asyncio.to_thread(elements[0].get_attribute, attribute)
                    if value:
                        return value.strip()
            except Exception:  # noqa: BLE001
                continue
        return ""

    async def list_attributes(self, selectors: Iterable[str], attribute: str) -> list[str]:
        values: list[str] = []
        for selector in selectors:
            try:
                elements = await asyncio.to_thread(self._find_elements, selector)
                for element in elements:
                    value = await asyncio.to_thread(element.get_attribute, attribute)
                    if value:
                        values.append(value.strip())
            except Exception:  # noqa: BLE001
                continue
        return values

    async def all_text_contents(self, selector: str) -> list[str]:
        try:
            elements = await asyncio.to_thread(self._find_elements, selector)
            values: list[str] = []
            for element in elements:
                text = await asyncio.to_thread(lambda e=element: e.text)
                if text and text.strip():
                    values.append(clean_extracted_text(text))
            return values
        except Exception:  # noqa: BLE001
            return []

    async def scroll_selector(self, selector: str, amount: int) -> None:
        await asyncio.to_thread(
            self.driver.execute_script,
            """
            const el = document.querySelector(arguments[0]);
            if (el) { el.scrollBy(0, arguments[1]); }
            """,
            selector,
            amount,
        )
        await self.wait_random(0.4, 1.0)

    async def scroll_page(self, amount: int) -> None:
        await asyncio.to_thread(self.driver.execute_script, "window.scrollBy(0, arguments[0]);", amount)
        await self.wait_random(0.4, 1.0)


async def create_browser_session(
    visible: bool,
    language: str,
    delay_min: float,
    delay_max: float,
    logger: Any,
) -> BaseMapsBrowser:
    playwright_browser = PlaywrightMapsBrowser(visible, language, delay_min, delay_max, logger)
    try:
        await playwright_browser.start()
        logger.info("Browser started with Playwright.")
        return playwright_browser
    except Exception as exc:  # noqa: BLE001
        logger.warning("Playwright launch failed. Falling back to Selenium. Reason: %s", exc)
        try:
            await playwright_browser.close()
        except Exception:  # noqa: BLE001
            pass

    selenium_browser = SeleniumMapsBrowser(visible, language, delay_min, delay_max, logger)
    await selenium_browser.start()
    logger.info("Browser started with undetected-chromedriver Selenium fallback.")
    return selenium_browser
