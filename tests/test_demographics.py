"""
Tests for the demographics / registration screen.

Run from web/ with:
    pytest tests/ -v           # headless
    pytest tests/ -v --headed  # visible browser
"""
import pytest
from playwright.sync_api import Page

BASE_URL = "http://localhost:8099"


# ── navigation helper ─────────────────────────────────────────────────────────

def reach_demographics(page: Page):
    """Navigate through welcome → cover → film selection → onboarding → demographics."""
    page.goto(BASE_URL)

    # Wait for JS to initialise and configs to load
    page.wait_for_function("() => typeof App !== 'undefined' && !!App.allConfigs")

    # Welcome screen: new users are redirected to cover-screen immediately by JS;
    # returning users see the welcome screen and need to click "Get started".
    if page.evaluate("() => document.getElementById('welcome-screen').classList.contains('active')"):
        page.locator("#btn-welcome-start").click()

    # Cover screen
    page.wait_for_function("() => document.getElementById('cover-screen').classList.contains('active')")
    page.locator("#btn-cover-continue").click()

    # Film selection screen
    page.wait_for_function("() => document.getElementById('film-screen').classList.contains('active')")
    page.locator("#lang-pair-buttons .btn-toggle").first.click()
    page.wait_for_selector("#film-list-buttons .film-select-btn", state="visible")
    page.locator("#film-list-buttons .film-select-btn").first.locator("strong").click()
    page.locator("#btn-film-continue").click()

    # Onboarding modal: advance each step, checking text BEFORE clicking
    page.wait_for_function("() => document.getElementById('onboarding-modal').classList.contains('open')")
    while True:
        next_btn = page.locator("#btn-onboarding-next")
        next_btn.wait_for(state="visible")
        is_done = next_btn.text_content().strip() == "Done"
        next_btn.click()
        if is_done:
            break

    # Demographics form
    page.wait_for_function("() => document.getElementById('login-screen').classList.contains('active')")
    page.wait_for_selector("#reg-name", state="visible")


# ── fill helper ───────────────────────────────────────────────────────────────

def fill_demographics(page: Page, *, name="Test", age="under25", gender="f",
                      native_src="yes", native_src_noread=None,
                      native_tgt="yes", professional="no", seen_film="yes"):
    """Fill the demographics form. native_src_noread must be set when native_src='no'."""
    if name:
        page.fill("#reg-name", name)

    page.locator(f"[data-field='age'][data-val='{age}']").click()
    page.locator(f"[data-field='gender'][data-val='{gender}']").click()
    page.locator(f"[data-field='professional'][data-val='{professional}']").click()

    # Native source language — inside #reg-native-src-group
    src_group = page.locator("#reg-native-src-group")
    if native_src == "yes":
        src_group.locator("[id$='-yes-btn']").first.click()
    else:
        src_group.locator("[id$='-no-btn']").first.click()
        # Secondary question is now visible; must answer it
        page.wait_for_selector("[id$='-secondary']", state="visible")
        if native_src_noread == "no":
            src_group.locator("[id$='-noread-yes']").first.click()  # "I don't read it at all"
        else:
            src_group.locator("[id$='-noread-no']").first.click()   # "I read some"

    # Native target language — inside #reg-native-tgt-group
    tgt_group = page.locator("#reg-native-tgt-group")
    if native_tgt == "yes":
        tgt_group.locator(".btn-choice").nth(0).click()
    else:
        tgt_group.locator(".btn-choice").nth(1).click()

    # Seen film — inside #reg-seen-films
    seen = page.locator("#reg-seen-films")
    seen.locator(f"[data-val='{seen_film}']").click()


def click_next(page: Page):
    page.locator("#btn-next-demographics").click()


def get_error(page: Page) -> str:
    return page.locator("#login-error").text_content().strip()


def on_walkthrough(page: Page) -> bool:
    return page.evaluate(
        "() => document.getElementById('walkthrough-screen').classList.contains('active')"
    )


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_storage(page: Page):
    page.goto(BASE_URL)
    page.evaluate("localStorage.clear()")
    yield


# ── happy-path tests ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("age,gender,professional", [
    ("25-34",  "m",  "no"),
    ("35-49",  "nb", "yes"),
    ("50plus", "na", "no"),
])
def test_demographic_variants(page: Page, age, gender, professional):
    """Every age value, every gender value, and professional=yes each appear at least once."""
    reach_demographics(page)
    fill_demographics(page, age=age, gender=gender, professional=professional)
    click_next(page)
    assert on_walkthrough(page)


def test_all_yes_proceeds(page: Page):
    reach_demographics(page)
    fill_demographics(page, native_src="yes", native_tgt="yes", seen_film="yes")
    click_next(page)
    assert on_walkthrough(page), "Expected walkthrough screen after valid submission"


def test_native_src_no_noread_proceeds(page: Page):
    """No native source + 'I don't read it at all' is a valid combination."""
    reach_demographics(page)
    fill_demographics(page, native_src="no", native_src_noread="no",
                      native_tgt="yes", seen_film="no")
    click_next(page)
    assert on_walkthrough(page)


def test_native_src_some_proceeds(page: Page):
    """No native source + 'I read some' is a valid combination."""
    reach_demographics(page)
    fill_demographics(page, native_src="no", native_src_noread="some",
                      native_tgt="no", seen_film="partially")
    click_next(page)
    assert on_walkthrough(page)


def test_all_no_proceeds(page: Page):
    """Answering No/minimum to every question should still be valid."""
    reach_demographics(page)
    fill_demographics(page, native_src="no", native_src_noread="no",
                      native_tgt="no", seen_film="no", professional="no")
    click_next(page)
    assert on_walkthrough(page)


# ── error / regression tests ──────────────────────────────────────────────────

def test_missing_name_blocked(page: Page):
    reach_demographics(page)
    fill_demographics(page, name="")
    click_next(page)
    assert "name" in get_error(page).lower()
    assert not on_walkthrough(page)


def test_missing_age_blocked(page: Page):
    reach_demographics(page)
    page.fill("#reg-name", "Test")
    # skip age, fill everything else
    page.locator("[data-field='gender'][data-val='f']").click()
    page.locator("[data-field='professional'][data-val='no']").click()
    page.locator("#reg-native-src-group [id$='-yes-btn']").first.click()
    page.locator("#reg-native-tgt-group .btn-choice").nth(0).click()
    page.locator("#reg-seen-films [data-val='yes']").click()
    click_next(page)
    assert get_error(page) != ""
    assert not on_walkthrough(page)


def test_missing_seen_film_blocked(page: Page):
    """Not answering the 'have you seen this film' question must block submission."""
    reach_demographics(page)
    page.fill("#reg-name", "Test")
    page.locator("[data-field='age'][data-val='under25']").click()
    page.locator("[data-field='gender'][data-val='f']").click()
    page.locator("[data-field='professional'][data-val='no']").click()
    page.locator("#reg-native-src-group [id$='-yes-btn']").first.click()
    page.locator("#reg-native-tgt-group .btn-choice").nth(0).click()
    # intentionally skip seen-film question
    click_next(page)
    assert get_error(page) != "", "Should error when seen-film question not answered"
    assert not on_walkthrough(page)


def test_missing_gender_blocked(page: Page):
    reach_demographics(page)
    page.fill("#reg-name", "Test")
    page.locator("[data-field='age'][data-val='under25']").click()
    # skip gender
    page.locator("[data-field='professional'][data-val='no']").click()
    page.locator("#reg-native-src-group [id$='-yes-btn']").first.click()
    page.locator("#reg-native-tgt-group .btn-choice").nth(0).click()
    page.locator("#reg-seen-films [data-val='yes']").click()
    click_next(page)
    assert get_error(page) != ""
    assert not on_walkthrough(page)


def test_missing_professional_blocked(page: Page):
    reach_demographics(page)
    page.fill("#reg-name", "Test")
    page.locator("[data-field='age'][data-val='under25']").click()
    page.locator("[data-field='gender'][data-val='f']").click()
    # skip professional
    page.locator("#reg-native-src-group [id$='-yes-btn']").first.click()
    page.locator("#reg-native-tgt-group .btn-choice").nth(0).click()
    page.locator("#reg-seen-films [data-val='yes']").click()
    click_next(page)
    assert get_error(page) != ""
    assert not on_walkthrough(page)


def test_missing_native_tgt_blocked(page: Page):
    reach_demographics(page)
    page.fill("#reg-name", "Test")
    page.locator("[data-field='age'][data-val='under25']").click()
    page.locator("[data-field='gender'][data-val='f']").click()
    page.locator("[data-field='professional'][data-val='no']").click()
    page.locator("#reg-native-src-group [id$='-yes-btn']").first.click()
    # skip native_tgt
    page.locator("#reg-seen-films [data-val='yes']").click()
    click_next(page)
    assert get_error(page) != ""
    assert not on_walkthrough(page)


def test_native_src_no_without_followup_blocked(page: Page):
    """Regression: clicking No for native source language WITHOUT answering
    the follow-up question must block submission."""
    reach_demographics(page)
    page.fill("#reg-name", "Test")
    page.locator("[data-field='age'][data-val='under25']").click()
    page.locator("[data-field='gender'][data-val='f']").click()
    page.locator("[data-field='professional'][data-val='no']").click()

    # Click No but intentionally skip the secondary question
    page.locator("#reg-native-src-group [id$='-no-btn']").first.click()

    page.locator("#reg-native-tgt-group .btn-choice").nth(0).click()
    page.locator("#reg-seen-films [data-val='yes']").click()

    click_next(page)
    assert get_error(page) != "", "Should error when native-src follow-up not answered"
    assert not on_walkthrough(page)
