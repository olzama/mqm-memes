"""Shared navigation helpers for all test modules."""
import pytest
from playwright.sync_api import Page

BASE_URL = "http://localhost:8099"


# ── navigation ────────────────────────────────────────────────────────────────

def reach_demographics(page: Page):
    """Navigate through welcome → cover → film selection → onboarding → demographics."""
    page.goto(BASE_URL)
    page.wait_for_function("() => typeof App !== 'undefined' && !!App.allConfigs")

    if page.evaluate("() => document.getElementById('welcome-screen').classList.contains('active')"):
        page.locator("#btn-welcome-start").click()

    page.wait_for_function("() => document.getElementById('cover-screen').classList.contains('active')")
    page.locator("#btn-cover-continue").click()

    page.wait_for_function("() => document.getElementById('film-screen').classList.contains('active')")
    page.locator("#lang-pair-buttons .btn-toggle").first.click()
    page.wait_for_selector("#film-list-buttons .film-select-btn", state="visible")
    page.locator("#film-list-buttons .film-select-btn").first.locator("strong").click()
    page.locator("#btn-film-continue").click()

    page.wait_for_function("() => document.getElementById('onboarding-modal').classList.contains('open')")
    while True:
        next_btn = page.locator("#btn-onboarding-next")
        next_btn.wait_for(state="visible")
        is_done = next_btn.text_content().strip() == "Done"
        next_btn.click()
        if is_done:
            break

    page.wait_for_function("() => document.getElementById('login-screen').classList.contains('active')")
    page.wait_for_selector("#reg-name", state="visible")


def fill_demographics(page: Page, *, name="Test", age="under25", gender="f",
                      native_src="yes", native_src_noread=None,
                      native_tgt="yes", professional="no", seen_film="yes"):
    """Fill the demographics form. native_src_noread must be set when native_src='no'."""
    if name:
        page.fill("#reg-name", name)

    page.locator(f"[data-field='age'][data-val='{age}']").click()
    page.locator(f"[data-field='gender'][data-val='{gender}']").click()
    page.locator(f"[data-field='professional'][data-val='{professional}']").click()

    src_group = page.locator("#reg-native-src-group")
    if native_src == "yes":
        src_group.locator("[id$='-yes-btn']").first.click()
    else:
        src_group.locator("[id$='-no-btn']").first.click()
        page.wait_for_selector("[id$='-secondary']", state="visible")
        if native_src_noread == "no":
            src_group.locator("[id$='-noread-yes']").first.click()
        else:
            src_group.locator("[id$='-noread-no']").first.click()

    tgt_group = page.locator("#reg-native-tgt-group")
    if native_tgt == "yes":
        tgt_group.locator(".btn-choice").nth(0).click()
    else:
        tgt_group.locator(".btn-choice").nth(1).click()

    seen = page.locator("#reg-seen-films")
    seen.locator(f"[data-val='{seen_film}']").click()


def click_next(page: Page):
    page.locator("#btn-next-demographics").click()


def reach_walkthrough(page: Page, *, native_src="yes", native_src_noread=None):
    """Navigate all the way to the walkthrough screen.

    native_src / native_src_noread map to proficiency values:
      native_src="yes"                          → proficiency 'yes'  → Version A
      native_src="no", native_src_noread=None   → proficiency 'some' → Version A
      native_src="no", native_src_noread="no"   → proficiency 'no'   → Version B
    """
    reach_demographics(page)
    fill_demographics(page, native_src=native_src, native_src_noread=native_src_noread)
    click_next(page)
    page.wait_for_function(
        "() => document.getElementById('walkthrough-screen').classList.contains('active')"
    )


def reach_eval(page: Page, *, native_src="yes"):
    """Navigate through walkthrough to the eval screen."""
    reach_walkthrough(page, native_src=native_src)
    while True:
        btn = page.locator("#btn-wt-next")
        btn.wait_for(state="visible")
        is_last = btn.text_content().strip() == "Start evaluation →"
        btn.click()
        if is_last:
            break
    page.wait_for_function(
        "() => document.getElementById('eval-screen').classList.contains('active')"
    )


# ── state queries ─────────────────────────────────────────────────────────────

def get_error(page: Page) -> str:
    return page.locator("#login-error").text_content().strip()


def on_screen(page: Page, screen_id: str) -> bool:
    return page.evaluate(
        f"() => document.getElementById('{screen_id}').classList.contains('active')"
    )


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_storage(page: Page):
    page.goto(BASE_URL)
    page.evaluate("localStorage.clear()")
    yield
