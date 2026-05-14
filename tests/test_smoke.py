"""Minimal smoke test — verifies pytest-playwright is installed and the dev server works."""
from playwright.sync_api import Page

BASE_URL = "http://localhost:8099"


def test_page_loads(page: Page):
    page.goto(BASE_URL)
    assert page.title() == "Subtitle Translation Evaluation"
    assert page.locator("#welcome-screen").is_visible()
