"""
Tests for the walkthrough screen (practice items shown after demographics).
"""
import pytest
from playwright.sync_api import Page
from tests.helpers import reach_walkthrough, on_screen

WT_TOTAL = 3

# Proficiency states and how to reach them via reach_walkthrough kwargs:
#   'yes'  → native_src="yes"               → Version A
#   'some' → native_src="no", noread=None   → Version A
#   'no'   → native_src="no", noread="no"   → Version B
PROFICIENCY_SETTINGS = {
    "yes":  dict(native_src="yes", native_src_noread=None),
    "some": dict(native_src="no",  native_src_noread=None),
    "no":   dict(native_src="no",  native_src_noread="no"),
}

# Version intro: (must_contain, must_not_contain) — both lowercase
INTRO_EXPECTATIONS = {
    "yes":  ("calibrate", "don't read"),
    "some": ("calibrate", "don't read"),
    "no":   ("don't read", "calibrate"),
}

# Card content per (proficiency, item_idx): (must_contain, must_not_contain)
# Issue labels are rendered uppercase (MAJOR/MINOR); categories are lowercase.
# Note text never uses uppercase MAJOR/MINOR, so that distinguishes labels from prose.
CARD_EXPECTATIONS = {
    ("yes",  0): (["No issues to mark"],                        ["MAJOR", "MINOR"]),
    ("yes",  1): (["MAJOR", "accuracy", "MINOR", "style"],      ["fluency"]),
    ("yes",  2): (["MAJOR", "style", "accuracy"],               ["fluency"]),
    ("some", 0): (["No issues to mark"],                        ["MAJOR", "MINOR"]),
    ("some", 1): (["MAJOR", "accuracy", "MINOR", "style"],      ["fluency"]),
    ("some", 2): (["MAJOR", "style", "accuracy"],               ["fluency"]),
    ("no",   0): (["No issues to mark"],                        ["MAJOR", "MINOR"]),
    ("no",   1): (["MAJOR", "fluency", "MINOR", "style"],       ["accuracy"]),
    ("no",   2): (["MAJOR", "style", "accuracy"],               ["fluency"]),
}


# ── helpers ───────────────────────────────────────────────────────────────────

def wt_counter(page: Page) -> str:
    return page.locator("#wt-counter").text_content().strip()


def wt_next_text(page: Page) -> str:
    return page.locator("#btn-wt-next").text_content().strip()


def wt_intro(page: Page) -> str:
    return page.locator("#wt-intro").inner_text().strip()


def wt_card(page: Page) -> str:
    return page.locator("#wt-card").inner_text().strip()


# ── intro version: all three proficiency states ───────────────────────────────

@pytest.mark.parametrize("proficiency,expected_in,not_in", [
    (p, ei, ni) for p, (ei, ni) in INTRO_EXPECTATIONS.items()
])
def test_intro_version(page: Page, proficiency, expected_in, not_in):
    reach_walkthrough(page, **PROFICIENCY_SETTINGS[proficiency])
    intro = wt_intro(page).lower()
    assert expected_in in intro
    assert not_in not in intro


# ── card content: all proficiency × item combinations ────────────────────────

@pytest.mark.parametrize("proficiency,item_idx", list(CARD_EXPECTATIONS.keys()))
def test_card_content(page: Page, proficiency, item_idx):
    reach_walkthrough(page, **PROFICIENCY_SETTINGS[proficiency])
    for _ in range(item_idx):
        page.locator("#btn-wt-next").click()
    card = wt_card(page)
    must_contain, must_not_contain = CARD_EXPECTATIONS[(proficiency, item_idx)]
    for text in must_contain:
        assert text in card, f"proficiency={proficiency} item={item_idx}: missing '{text}'"
    for text in must_not_contain:
        assert text not in card, f"proficiency={proficiency} item={item_idx}: unexpected '{text}'"


# ── navigation mechanics ──────────────────────────────────────────────────────

def test_starts_at_item_1(page: Page):
    reach_walkthrough(page)
    assert wt_counter(page) == f"Item 1 of {WT_TOTAL}"


def test_next_advances_counter(page: Page):
    reach_walkthrough(page)
    page.locator("#btn-wt-next").click()
    assert wt_counter(page) == f"Item 2 of {WT_TOTAL}"


def test_button_text_progression(page: Page):
    """Button reads 'Next' for all items except the last, which reads 'Start evaluation →'."""
    reach_walkthrough(page)
    for _ in range(WT_TOTAL - 1):
        assert wt_next_text(page) == "Next"
        page.locator("#btn-wt-next").click()
    assert wt_next_text(page) == "Start evaluation →"


def test_card_content_changes_between_items(page: Page):
    reach_walkthrough(page)
    card1 = wt_card(page)
    page.locator("#btn-wt-next").click()
    assert wt_card(page) != card1


# ── integration ───────────────────────────────────────────────────────────────

def test_completes_to_eval_screen(page: Page):
    """Clicking through all walkthrough items reaches the eval screen."""
    reach_walkthrough(page)
    while True:
        btn = page.locator("#btn-wt-next")
        is_last = btn.text_content().strip() == "Start evaluation →"
        btn.click()
        if is_last:
            break
    page.wait_for_function(
        "() => document.getElementById('eval-screen').classList.contains('active')"
    )
    assert on_screen(page, "eval-screen")
