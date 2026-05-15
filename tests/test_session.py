"""
Tests for session persistence, the back button, and slider navigation.
"""
import pytest
from playwright.sync_api import Page
from tests.helpers import BASE_URL, reach_eval, on_screen


# ── helpers ────────────────────────────────────────────────────────────────────

def save_item_with_issue(page: Page) -> None:
    """Add one issue to the current item and click Save & next."""
    page.locator("#sev-group [data-value='major']").click()
    page.locator("#cat-group [data-value='accuracy']").click()
    page.locator("#btn-add-issue").click()
    page.locator("#btn-save").click()


def progress_label(page: Page) -> str:
    return page.locator("#progress-label").text_content().strip()


def issue_count(page: Page) -> int:
    return page.locator("#issue-list .issue-item").count()


# ── returning user: UI ────────────────────────────────────────────────────────

def test_returning_user_ui_after_session_created(page: Page):
    """After completing registration and entering eval, reloading shows the returning-user UI."""
    reach_eval(page)
    page.goto(BASE_URL)
    page.wait_for_function("() => typeof App !== 'undefined' && !!App.allConfigs")
    assert page.locator("#welcome-returning").is_visible()
    assert not page.locator("#welcome-new").is_visible()


def test_returning_user_name_displayed(page: Page):
    """The welcome-back greeting shows the evaluator's name."""
    reach_eval(page)
    evaluator_name = page.evaluate(
        "() => App.session.evaluator_meta && App.session.evaluator_meta.name"
    )
    page.goto(BASE_URL)
    page.wait_for_function("() => typeof App !== 'undefined' && !!App.allConfigs")
    displayed = page.locator("#welcome-name-display").text_content().strip()
    assert displayed == evaluator_name


def test_resume_reaches_eval_screen(page: Page):
    """Clicking Resume on the welcome screen lands on the eval screen."""
    reach_eval(page)
    page.goto(BASE_URL)
    page.wait_for_function("() => typeof App !== 'undefined' && !!App.allConfigs")
    page.locator("#btn-welcome-resume").click()
    page.wait_for_function(
        "() => document.getElementById('eval-screen').classList.contains('active')"
    )
    assert on_screen(page, "eval-screen")


def test_resume_restores_progress_position(page: Page):
    """After judging item 1 and reloading, Resume should restore slider at position 2."""
    reach_eval(page)
    page.locator("#btn-no-issues").click()   # judge item 1 → advances to item 2
    page.goto(BASE_URL)
    page.wait_for_function("() => typeof App !== 'undefined' && !!App.allConfigs")
    page.locator("#btn-welcome-resume").click()
    page.wait_for_function(
        "() => document.getElementById('eval-screen').classList.contains('active')"
    )
    label = progress_label(page)
    pos = int(label.split(" / ")[0])
    assert pos == 2


def test_new_session_after_i_am_different_person(page: Page):
    """'I'm a different person' on the welcome screen lets a new user go through onboarding."""
    reach_eval(page)
    page.goto(BASE_URL)
    page.wait_for_function("() => typeof App !== 'undefined' && !!App.allConfigs")
    # Welcome screen shows returning UI; decline it
    page.locator("#btn-welcome-new-user").click()
    page.wait_for_function(
        "() => document.getElementById('cover-screen').classList.contains('active')"
    )
    page.locator("#btn-cover-continue").click()
    page.wait_for_function(
        "() => document.getElementById('film-screen').classList.contains('active')"
    )
    page.locator("#lang-pair-buttons .btn-toggle").first.click()
    page.wait_for_selector("#film-list-buttons .film-select-btn", state="visible")
    page.locator("#film-list-buttons .film-select-btn").first.locator("strong").click()
    page.locator("#btn-film-continue").click()
    # A different person (App.evaluatorId null) must go through onboarding, not be fast-tracked
    page.wait_for_function(
        "() => document.getElementById('onboarding-modal').classList.contains('open')"
    )
    assert page.locator("#onboarding-modal").evaluate("el => el.classList.contains('open')")


# ── back button ───────────────────────────────────────────────────────────────

def test_back_button_restores_saved_issues(page: Page):
    """After saving item 1 with an issue, clicking Back pre-populates the issue list."""
    reach_eval(page)
    save_item_with_issue(page)   # now on item 2
    page.wait_for_selector("#btn-back", state="visible")
    page.locator("#btn-back").click()
    # Should be back at item 1 with the saved issue
    assert int(progress_label(page).split(" / ")[0]) == 1
    assert issue_count(page) == 1


def test_back_button_shows_editing_banner(page: Page):
    """Going back to a judged item shows the 'Editing a saved judgment' banner."""
    reach_eval(page)
    save_item_with_issue(page)
    page.locator("#btn-back").click()
    prev_text = page.locator("#prev-summary-text").text_content().strip()
    assert "Editing" in prev_text or "saved judgment" in prev_text.lower()


def test_back_button_disabled_on_first_item(page: Page):
    """On the very first item, the back button is hidden (prev-summary is hidden)."""
    reach_eval(page)
    assert not page.locator("#prev-summary").is_visible()


# ── slider navigation ─────────────────────────────────────────────────────────

def test_slider_navigates_back_to_judged_item(page: Page):
    """Dragging the slider to a previously judged position reloads that item."""
    reach_eval(page)
    original_text = page.locator("#original-text").text_content().strip()
    save_item_with_issue(page)   # now on item 2
    # Move slider back to 1
    page.locator("#progress-slider").evaluate(
        "el => { el.value = 1; el.dispatchEvent(new Event('input')); }"
    )
    assert int(progress_label(page).split(" / ")[0]) == 1
    assert page.locator("#original-text").text_content().strip() == original_text


def test_slider_shows_saved_issues_on_revisit(page: Page):
    """A revisited item (via slider) has its saved issues pre-populated."""
    reach_eval(page)
    save_item_with_issue(page)   # judge item 1: 1 issue
    page.locator("#btn-no-issues").click()  # judge item 2: no issues → now on item 3
    # Drag slider back to item 1
    page.locator("#progress-slider").evaluate(
        "el => { el.value = 1; el.dispatchEvent(new Event('input')); }"
    )
    assert issue_count(page) == 1


# ── login-screen returning user ───────────────────────────────────────────────

def _create_session(page: Page) -> str:
    """Navigate to eval screen (saves session to localStorage). Returns evaluator name."""
    reach_eval(page)
    return page.evaluate(
        "() => App.session.evaluator_meta && App.session.evaluator_meta.name"
    )


def _navigate_back_to_login(page: Page) -> None:
    """Reload the page (clears App.evaluatorId), decline Resume, go through film+onboarding."""
    # Reload so App.evaluatorId is null — this is when a returning user would see #login-returning
    page.goto(BASE_URL)
    page.wait_for_function("() => typeof App !== 'undefined' && !!App.allConfigs")
    # Welcome screen shows returning-user UI; click "I'm a different person" to go to film screen
    # (App.evaluatorId stays null; LAST_ID_KEY should be preserved so login screen can find it)
    page.locator("#btn-welcome-new-user").click()
    page.wait_for_function(
        "() => document.getElementById('cover-screen').classList.contains('active')"
    )
    page.locator("#btn-cover-continue").click()
    page.wait_for_function(
        "() => document.getElementById('film-screen').classList.contains('active')"
    )
    # Select the same film and lang pair as the completed session
    page.locator("#lang-pair-buttons .btn-toggle").first.click()
    page.wait_for_selector("#film-list-buttons .film-select-btn", state="visible")
    page.locator("#film-list-buttons .film-select-btn").first.locator("strong").click()
    page.locator("#btn-film-continue").click()
    # App.evaluatorId is null → onboarding opens (not startOrResume)
    page.wait_for_function(
        "() => document.getElementById('onboarding-modal').classList.contains('open')"
    )
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


def test_login_returning_ui_shown_for_known_evaluator(page: Page):
    """Returning to the same film after a previous session shows #login-returning."""
    _create_session(page)
    _navigate_back_to_login(page)
    assert page.locator("#login-returning").is_visible()
    assert not page.locator("#login-new").is_visible()


def test_login_returning_name_displayed(page: Page):
    """The login-screen returning greeting shows the correct evaluator name."""
    name = _create_session(page)
    _navigate_back_to_login(page)
    displayed = page.locator("#login-name-display").text_content().strip()
    assert displayed == name


def test_login_returning_resume_reaches_eval(page: Page):
    """Clicking Resume on the login-screen returning UI reaches the eval screen."""
    _create_session(page)
    _navigate_back_to_login(page)
    assert page.locator("#login-returning").is_visible(), "#login-returning not shown"
    page.locator("#btn-resume").click()
    page.wait_for_function(
        "() => document.getElementById('eval-screen').classList.contains('active') || "
        "document.getElementById('complete-screen').classList.contains('active')"
    )
    assert on_screen(page, "eval-screen") or on_screen(page, "complete-screen")


def test_login_new_user_button_shows_form(page: Page):
    """'I'm a different person' on the login screen hides returning UI and shows the form."""
    _create_session(page)
    _navigate_back_to_login(page)
    assert page.locator("#login-returning").is_visible(), "#login-returning not shown"
    page.locator("#btn-new-user").click()
    assert page.locator("#login-new").is_visible()
    assert not page.locator("#login-returning").is_visible()


def test_slider_cannot_reach_unjudged_items(page: Page):
    """Dragging past the frontier snaps back to the frontier."""
    reach_eval(page)
    total = int(progress_label(page).split(" / ")[1])
    # Try to drag to the last item (unjudged)
    page.locator("#progress-slider").evaluate(
        f"el => {{ el.value = {total}; el.dispatchEvent(new Event('input')); }}"
    )
    # Frontier is 1 (nothing judged yet), so slider should snap back to 1
    assert int(progress_label(page).split(" / ")[0]) == 1
