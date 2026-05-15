"""
Tests for the welcome screen, cover screen, film selection screen, and onboarding modal.
"""
import json
import pytest
from playwright.sync_api import Page
from tests.helpers import BASE_URL, on_screen


# ── welcome screen: new user ──────────────────────────────────────────────────

def test_new_user_sees_get_started(page: Page):
    """Fresh load (no localStorage) shows the new-user UI, not the returning-user UI."""
    page.goto(BASE_URL)
    page.wait_for_function("() => typeof App !== 'undefined' && !!App.allConfigs")
    assert page.locator("#welcome-new").is_visible()
    assert not page.locator("#welcome-returning").is_visible()


def test_get_started_reaches_cover(page: Page):
    page.goto(BASE_URL)
    page.wait_for_function("() => typeof App !== 'undefined' && !!App.allConfigs")
    page.locator("#btn-welcome-start").click()
    page.wait_for_function("() => document.getElementById('cover-screen').classList.contains('active')")
    assert on_screen(page, "cover-screen")
    assert not on_screen(page, "welcome-screen")


# ── film selection screen ─────────────────────────────────────────────────────

def _reach_film_screen(page: Page):
    page.goto(BASE_URL)
    page.wait_for_function("() => typeof App !== 'undefined' && !!App.allConfigs")
    if page.evaluate("() => document.getElementById('welcome-screen').classList.contains('active')"):
        page.locator("#btn-welcome-start").click()
    page.wait_for_function("() => document.getElementById('cover-screen').classList.contains('active')")
    page.locator("#btn-cover-continue").click()
    page.wait_for_function("() => document.getElementById('film-screen').classList.contains('active')")


def test_film_continue_disabled_before_selection(page: Page):
    _reach_film_screen(page)
    assert page.locator("#btn-film-continue").is_disabled()


def test_lang_pair_buttons_present(page: Page):
    _reach_film_screen(page)
    assert page.locator("#lang-pair-buttons .btn-toggle").count() >= 1


def test_all_configured_lang_pairs_shown(page: Page):
    """Every target language present in configs.json appears as a lang-pair button."""
    _reach_film_screen(page)
    # Collect expected target languages from configs
    configs = page.evaluate("() => App.allConfigs")
    expected_targets = set()
    for film_cfg in configs.values():
        for model_cfg in (film_cfg.get("models") or {}).values():
            for tl in model_cfg.get("target_langs") or []:
                expected_targets.add(tl["lang"])
    # Every expected target language should appear in at least one button label
    buttons_text = page.locator("#lang-pair-buttons .btn-toggle").all_text_contents()
    for lang in expected_targets:
        assert any(lang in btn for btn in buttons_text), \
            f"Expected lang '{lang}' not found in lang-pair buttons: {buttons_text}"


def test_film_list_hidden_before_lang_pair(page: Page):
    _reach_film_screen(page)
    assert not page.locator("#film-list-group").is_visible()


def test_selecting_lang_pair_shows_films(page: Page):
    _reach_film_screen(page)
    page.locator("#lang-pair-buttons .btn-toggle").first.click()
    page.wait_for_selector("#film-list-buttons .film-select-btn", state="visible")
    assert page.locator("#film-list-buttons .film-select-btn").count() >= 1


def test_film_continue_enabled_after_film_selection(page: Page):
    _reach_film_screen(page)
    page.locator("#lang-pair-buttons .btn-toggle").first.click()
    page.wait_for_selector("#film-list-buttons .film-select-btn", state="visible")
    page.locator("#film-list-buttons .film-select-btn").first.locator("strong").click()
    assert page.locator("#btn-film-continue").is_enabled()


def test_different_lang_pairs_show_different_films(page: Page):
    """Switching lang pair updates the film list."""
    _reach_film_screen(page)
    buttons = page.locator("#lang-pair-buttons .btn-toggle")
    if buttons.count() < 2:
        pytest.skip("Only one lang pair configured")
    buttons.nth(0).click()
    page.wait_for_selector("#film-list-buttons .film-select-btn", state="visible")
    films_a = set(page.locator("#film-list-buttons .film-select-btn strong").all_text_contents())
    buttons.nth(1).click()
    page.wait_for_selector("#film-list-buttons .film-select-btn", state="visible")
    films_b = set(page.locator("#film-list-buttons .film-select-btn strong").all_text_contents())
    assert films_a != films_b


# ── onboarding modal ──────────────────────────────────────────────────────────

def _reach_onboarding(page: Page):
    _reach_film_screen(page)
    page.locator("#lang-pair-buttons .btn-toggle").first.click()
    page.wait_for_selector("#film-list-buttons .film-select-btn", state="visible")
    page.locator("#film-list-buttons .film-select-btn").first.locator("strong").click()
    page.locator("#btn-film-continue").click()
    page.wait_for_function(
        "() => document.getElementById('onboarding-modal').classList.contains('open')"
    )


def test_onboarding_modal_opens_after_film_selection(page: Page):
    _reach_onboarding(page)
    assert page.locator("#onboarding-modal").evaluate(
        "el => el.classList.contains('open')"
    )


def test_onboarding_next_button_visible(page: Page):
    _reach_onboarding(page)
    assert page.locator("#btn-onboarding-next").is_visible()


def test_onboarding_last_step_says_done(page: Page):
    """Clicking through all onboarding steps reaches a 'Done' button."""
    _reach_onboarding(page)
    for _ in range(20):  # safety cap
        btn = page.locator("#btn-onboarding-next")
        btn.wait_for(state="visible")
        if btn.text_content().strip() == "Done":
            break
        btn.click()
    assert page.locator("#btn-onboarding-next").text_content().strip() == "Done"


def test_onboarding_done_closes_modal_and_reaches_demographics(page: Page):
    _reach_onboarding(page)
    while True:
        btn = page.locator("#btn-onboarding-next")
        btn.wait_for(state="visible")
        is_done = btn.text_content().strip() == "Done"
        btn.click()
        if is_done:
            break
    page.wait_for_function(
        "() => document.getElementById('login-screen').classList.contains('active')"
    )
    assert on_screen(page, "login-screen")
    assert not page.locator("#onboarding-modal").evaluate(
        "el => el.classList.contains('open')"
    )
