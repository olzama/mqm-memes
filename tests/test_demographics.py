"""
Tests for the demographics / registration screen.

Run from web/ with:
    pytest tests/ -v           # headless
    pytest tests/ -v --headed  # visible browser
"""
import itertools
import pytest
from playwright.sync_api import Page
from tests.helpers import (
    reach_demographics, fill_demographics, click_next, get_error, on_screen
)

ERR_NAME    = "Please enter your name or initials."
ERR_MISSING = "Please answer all questions."


def on_walkthrough(page: Page) -> bool:
    return on_screen(page, "walkthrough-screen")


def on_login(page: Page) -> bool:
    return on_screen(page, "login-screen")


# ── happy-path: all combinations of the branching fields ─────────────────────
#
# native_src state  native_src_noread  → proficiency stored in App.regState
#   "yes"           None               → 'yes'  (Version A)
#   "no"            None               → 'some' (Version A)
#   "no"            "no"               → 'no'   (Version B)

NATIVE_SRC_STATES = [
    ("yes", None),   # proficiency 'yes'
    ("no",  None),   # proficiency 'some'
    ("no",  "no"),   # proficiency 'no'
]
NATIVE_TGT_VALUES = ["yes", "no"]
SEEN_FILM_VALUES  = ["yes", "no", "partially"]

@pytest.mark.parametrize(
    "native_src,native_src_noread,native_tgt,seen_film",
    [
        (ns, nr, nt, sf)
        for (ns, nr), nt, sf in itertools.product(
            NATIVE_SRC_STATES, NATIVE_TGT_VALUES, SEEN_FILM_VALUES
        )
    ],
)
def test_valid_submission(page: Page, native_src, native_src_noread, native_tgt, seen_film):
    """All 18 combinations of the three branching fields must produce a valid submission."""
    reach_demographics(page)
    fill_demographics(page, native_src=native_src, native_src_noread=native_src_noread,
                      native_tgt=native_tgt, seen_film=seen_film)
    click_next(page)
    assert on_walkthrough(page)


# ── happy-path: all values for the simple (non-branching) fields ──────────────

@pytest.mark.parametrize("age,gender,professional", [
    ("under25", "f",  "no"),
    ("25-34",   "m",  "no"),
    ("35-49",   "nb", "yes"),
    ("50plus",  "na", "no"),
])
def test_demographic_field_values(page: Page, age, gender, professional):
    """Every age value, every gender value, and professional=yes each appear at least once."""
    reach_demographics(page)
    fill_demographics(page, age=age, gender=gender, professional=professional)
    click_next(page)
    assert on_walkthrough(page)


# ── error tests: each required field missing blocks submission ─────────────────

def test_empty_form_blocked(page: Page):
    """Submitting without touching anything at all must show the name error first."""
    reach_demographics(page)
    click_next(page)
    assert get_error(page) == ERR_NAME
    assert on_login(page)
    assert not on_walkthrough(page)


def test_missing_name_blocked(page: Page):
    reach_demographics(page)
    fill_demographics(page, name="")
    click_next(page)
    assert get_error(page) == ERR_NAME
    assert on_login(page)
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
    assert get_error(page) == ERR_MISSING
    assert on_login(page)
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
    assert get_error(page) == ERR_MISSING
    assert on_login(page)
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
    assert get_error(page) == ERR_MISSING
    assert on_login(page)
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
    assert get_error(page) == ERR_MISSING
    assert on_login(page)
    assert not on_walkthrough(page)


def test_missing_seen_film_blocked(page: Page):
    reach_demographics(page)
    page.fill("#reg-name", "Test")
    page.locator("[data-field='age'][data-val='under25']").click()
    page.locator("[data-field='gender'][data-val='f']").click()
    page.locator("[data-field='professional'][data-val='no']").click()
    page.locator("#reg-native-src-group [id$='-yes-btn']").first.click()
    page.locator("#reg-native-tgt-group .btn-choice").nth(0).click()
    # skip seen_film
    click_next(page)
    assert get_error(page) == ERR_MISSING
    assert on_login(page)
    assert not on_walkthrough(page)


def test_native_src_no_without_followup_blocked(page: Page):
    """Regression: clicking No for native source WITHOUT answering the follow-up blocks submission."""
    reach_demographics(page)
    page.fill("#reg-name", "Test")
    page.locator("[data-field='age'][data-val='under25']").click()
    page.locator("[data-field='gender'][data-val='f']").click()
    page.locator("[data-field='professional'][data-val='no']").click()
    page.locator("#reg-native-src-group [id$='-no-btn']").first.click()
    # intentionally skip secondary question
    page.locator("#reg-native-tgt-group .btn-choice").nth(0).click()
    page.locator("#reg-seen-films [data-val='yes']").click()
    click_next(page)
    assert get_error(page) == ERR_MISSING
    assert on_login(page)
    assert not on_walkthrough(page)
