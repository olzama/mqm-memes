"""
Tests for setting aside and restoring sessions when a film's configured models change.
"""
import json
from playwright.sync_api import Page
from tests.helpers import BASE_URL, on_screen

FILM = "carnival-night"
LANG = "eng"
EVAL_ID = "restoretest-0001"
KEY = f"subtitle-eval-{EVAL_ID}-{FILM}-{LANG}"


def _start(page: Page) -> None:
    """Load the app and start or resume EVAL_ID's session for FILM directly."""
    page.goto(BASE_URL)
    page.wait_for_function("() => typeof App !== 'undefined' && !!App.allConfigs")
    page.evaluate(
        """([id, film, lang]) => {
            App.evaluatorId = id;
            App.evaluatorMeta = { name: 'Restore Test' };
            App.selectedFilm = film;
            App.selectedTargetLangCode = lang;
            App.selectedTargetLang = 'English';
            return startOrResume(id);
        }""",
        [EVAL_ID, FILM, LANG],
    )
    assert on_screen(page, "eval-screen"), "eval screen not reached"


def _configured_models(page: Page) -> list:
    return page.evaluate(f"() => Object.keys(App.allConfigs['{FILM}'].models)")


def _judge_first_item(page: Page) -> None:
    page.locator("#sev-group [data-value='major']").click()
    page.locator("#cat-group [data-value='accuracy']").click()
    page.locator("#btn-add-issue").click()
    page.locator("#btn-save").click()


def _stored(page: Page, key: str):
    raw = page.evaluate("k => localStorage.getItem(k)", key)
    return json.loads(raw) if raw else None


def _archive_keys(page: Page) -> list:
    return page.evaluate(
        """prefix => Object.keys(localStorage).filter(k => k.startsWith(prefix))""",
        f"{KEY}-archived-",
    )


def _session_with_model(session: dict, model: str) -> dict:
    s = json.loads(json.dumps(session))
    for t in s["tasks"]:
        t["trans_model"] = model
    s["judgments"] = {}
    return s


def test_archived_session_restored_when_its_models_return(page: Page):
    """A session archived earlier is resumed, judgments intact, once its models are configured again."""
    _start(page)
    _judge_first_item(page)
    original = _stored(page, KEY)
    assert original["judgments"], "judgment was not saved"

    # Earlier state: the original session sits in the archive, and the live key holds
    # a session built from a model the film no longer lists.
    page.evaluate(
        """([key, orig, other]) => {
            localStorage.setItem(key + '-archived-1760000000000', JSON.stringify(orig));
            localStorage.setItem(key, JSON.stringify(other));
        }""",
        [KEY, original, _session_with_model(original, "no-longer-configured")],
    )

    _start(page)
    restored = page.evaluate("() => App.session")
    assert restored["judgments"] == original["judgments"]
    assert restored["created"] == original["created"]
    assert _stored(page, KEY)["created"] == original["created"]
    # The archive is kept, and the session that was just replaced is archived as well.
    assert len(_archive_keys(page)) == 2


def test_archive_with_unconfigured_models_not_restored(page: Page):
    """An archived session whose models are still not configured stays archived."""
    _start(page)
    fresh = _stored(page, KEY)
    stale = _session_with_model(fresh, "no-longer-configured")
    stale["created"] = "2000-01-01T00:00:00.000Z"
    page.evaluate(
        """([key, stale]) => {
            localStorage.removeItem(key);
            localStorage.setItem(key + '-archived-1760000000000', JSON.stringify(stale));
        }""",
        [KEY, stale],
    )

    _start(page)
    session = page.evaluate("() => App.session")
    assert session["created"] != stale["created"]
    assert all(t["trans_model"] in _configured_models(page) for t in session["tasks"])
    assert len(_archive_keys(page)) == 1


def test_newest_matching_archive_restored(page: Page):
    """With several restorable archives, the most recently archived one is resumed."""
    _start(page)
    base = _stored(page, KEY)
    older = dict(base, created="2026-01-01T00:00:00.000Z")
    newer = dict(base, created="2026-02-01T00:00:00.000Z")
    page.evaluate(
        """([key, older, newer]) => {
            localStorage.removeItem(key);
            localStorage.setItem(key + '-archived-1760000000000', JSON.stringify(older));
            localStorage.setItem(key + '-archived-1770000000000', JSON.stringify(newer));
        }""",
        [KEY, older, newer],
    )

    _start(page)
    assert page.evaluate("() => App.session.created") == newer["created"]
