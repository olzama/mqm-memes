"""
Tests for the evaluation screen, inconsistency review screen, and complete screen.
"""
import pytest
from playwright.sync_api import Page
from tests.helpers import reach_eval, on_screen

SEVERITIES = ["major", "minor"]
CATEGORIES = ["accuracy", "fluency", "style", "terminology", "other"]

# (key, group_id, data-value, expected active class)
KEY_SHORTCUTS = [
    ("M", "sev-group", "major",       "active-major"),
    ("m", "sev-group", "minor",       "active-minor"),
    ("a", "cat-group", "accuracy",    "active-cat"),
    ("f", "cat-group", "fluency",     "active-cat"),
    ("s", "cat-group", "style",       "active-cat"),
    ("t", "cat-group", "terminology", "active-cat"),
    ("o", "cat-group", "other",       "active-cat"),
]


# ── local helpers ─────────────────────────────────────────────────────────────

def add_issue(page: Page, severity: str = "major", category: str = "accuracy",
              justification: str = "") -> None:
    page.locator(f"#sev-group [data-value='{severity}']").click()
    page.locator(f"#cat-group [data-value='{category}']").click()
    if justification:
        page.fill("#just-input", justification)
    page.locator("#btn-add-issue").click()


def progress_label(page: Page) -> str:
    return page.locator("#progress-label").text_content().strip()


def issue_count(page: Page) -> int:
    return page.locator("#issue-list .issue-item").count()


def judge_all_no_issues(page: Page) -> None:
    """Pre-fill every judgment with 'no issues' via JS, then trigger startReview."""
    page.evaluate("""
        () => {
            App.session.tasks.forEach((t, i) => {
                App.session.judgments[String(i)] = { issues: [], viewed_analysis: false };
            });
            saveSession();
            startReview();
        }
    """)


def inject_inconsistency_and_review(page: Page) -> None:
    """Find a repeat pair, judge them inconsistently, fill rest with no-issues, trigger review."""
    page.evaluate("""
        () => {
            const tasks = App.session.tasks;
            let pairA = null, pairB = null;
            outer: for (let i = 0; i < tasks.length; i++) {
                for (let j = i + 1; j < tasks.length; j++) {
                    if (tasks[i].film    === tasks[j].film    &&
                        tasks[i].item_id === tasks[j].item_id &&
                        tasks[i].method  === tasks[j].method  &&
                        tasks[i].run     === tasks[j].run) {
                        pairA = i; pairB = j; break outer;
                    }
                }
            }
            if (pairA === null) throw new Error('No repeat pair found in session');
            App.session.judgments[String(pairA)] = { issues: [], viewed_analysis: false };
            App.session.judgments[String(pairB)] = {
                issues: [{ severity: 'major', category: 'accuracy', span: '', justification: '' }],
                viewed_analysis: false
            };
            tasks.forEach((t, i) => {
                if (!App.session.judgments[String(i)])
                    App.session.judgments[String(i)] = { issues: [], viewed_analysis: false };
            });
            saveSession();
            startReview();
        }
    """)


# ── screen structure ──────────────────────────────────────────────────────────

def test_eval_original_text_populated(page: Page):
    reach_eval(page)
    assert page.locator("#original-text").text_content().strip() != ""


def test_eval_translation_text_populated(page: Page):
    reach_eval(page)
    assert page.locator("#translation-text").text_content().strip() != ""


def test_eval_progress_starts_at_one(page: Page):
    reach_eval(page)
    assert progress_label(page).startswith("1 / ")


def test_eval_no_issues_note_visible_initially(page: Page):
    reach_eval(page)
    assert page.locator("#no-issues-note").is_visible()
    assert issue_count(page) == 0


def test_eval_prev_summary_hidden_initially(page: Page):
    reach_eval(page)
    assert not page.locator("#prev-summary").is_visible()


# ── issue form: all severity × category combinations ─────────────────────────

@pytest.mark.parametrize("severity,category", [
    (s, c) for s in SEVERITIES for c in CATEGORIES
])
def test_add_issue_all_combos(page: Page, severity, category):
    """All 10 severity × category combinations add exactly one issue."""
    reach_eval(page)
    add_issue(page, severity=severity, category=category)
    assert issue_count(page) == 1
    assert page.locator("#no-issues-note").is_hidden()
    badge_text = page.locator("#issue-list .issue-item .badge").first.text_content().strip()
    assert badge_text == severity


def test_add_issue_clears_form(page: Page):
    reach_eval(page)
    add_issue(page)
    assert page.locator("#sev-group .active-major, #sev-group .active-minor").count() == 0
    assert page.locator("#cat-group .active-cat").count() == 0


def test_add_issue_with_justification(page: Page):
    reach_eval(page)
    add_issue(page, severity="minor", category="style", justification="test reason")
    assert "test reason" in page.locator("#issue-list .issue-item").first.text_content()


def test_add_multiple_issues(page: Page):
    reach_eval(page)
    add_issue(page, severity="major", category="accuracy")
    add_issue(page, severity="minor", category="style")
    assert issue_count(page) == 2


def test_add_issue_no_severity_blocked(page: Page):
    reach_eval(page)
    page.locator("#cat-group [data-value='accuracy']").click()
    page.locator("#btn-add-issue").click()
    assert issue_count(page) == 0


def test_add_issue_no_category_blocked(page: Page):
    reach_eval(page)
    page.locator("#sev-group [data-value='major']").click()
    page.locator("#btn-add-issue").click()
    assert issue_count(page) == 0


def test_remove_issue(page: Page):
    reach_eval(page)
    add_issue(page)
    assert issue_count(page) == 1
    page.locator("#issue-list .btn-remove").first.click()
    assert issue_count(page) == 0
    assert page.locator("#no-issues-note").is_visible()


# ── action buttons ────────────────────────────────────────────────────────────

def test_no_issues_advances_item(page: Page):
    reach_eval(page)
    total = progress_label(page).split(" / ")[1]
    page.locator("#btn-no-issues").click()
    assert progress_label(page) == f"2 / {total}"


def test_no_issues_shows_prev_summary(page: Page):
    reach_eval(page)
    page.locator("#btn-no-issues").click()
    assert page.locator("#prev-summary").is_visible()


def test_save_with_issues_advances_item(page: Page):
    reach_eval(page)
    add_issue(page)
    total = progress_label(page).split(" / ")[1]
    page.locator("#btn-save").click()
    assert progress_label(page) == f"2 / {total}"


def test_save_autocommits_partial_form(page: Page):
    """Clicking Save with sev+cat selected but not yet added auto-commits the partial issue."""
    reach_eval(page)
    page.locator("#sev-group [data-value='major']").click()
    page.locator("#cat-group [data-value='accuracy']").click()
    # intentionally do NOT click btn-add-issue
    total = progress_label(page).split(" / ")[1]
    page.locator("#btn-save").click()
    assert progress_label(page) == f"2 / {total}"
    # prev-summary should show a non-empty judgment, not "No issues"
    summary = page.locator("#prev-summary-text").text_content().strip()
    assert summary != "No issues"


def test_skip_reduces_total(page: Page):
    reach_eval(page)
    total_before = int(progress_label(page).split(" / ")[1])
    page.locator("#btn-skip").click()
    total_after = int(progress_label(page).split(" / ")[1])
    assert total_after == total_before - 1


# ── context / analysis toggles ────────────────────────────────────────────────

def test_context_toggle_opens_and_closes(page: Page):
    reach_eval(page)
    btn  = page.locator("#btn-show-context")
    body = page.locator("#context-body")
    assert not body.evaluate("el => el.classList.contains('open')")
    btn.click()
    assert body.evaluate("el => el.classList.contains('open')")
    assert btn.text_content().strip() == "Hide context"
    btn.click()
    assert not body.evaluate("el => el.classList.contains('open')")
    assert btn.text_content().strip() == "Show context"


def test_analysis_toggle_opens_and_closes(page: Page):
    reach_eval(page)
    btn  = page.locator("#btn-show-analysis")
    body = page.locator("#analysis-body")
    assert not body.evaluate("el => el.classList.contains('open')")
    btn.click()
    assert body.evaluate("el => el.classList.contains('open')")
    assert "Hide analysis" in btn.text_content()
    btn.click()
    assert not body.evaluate("el => el.classList.contains('open')")


# ── keyboard shortcuts ────────────────────────────────────────────────────────

@pytest.mark.parametrize("key,group_id,value,active_class", KEY_SHORTCUTS)
def test_keyboard_selects_button(page: Page, key, group_id, value, active_class):
    reach_eval(page)
    page.keyboard.press(key)
    classes = page.locator(f"#{group_id} [data-value='{value}']").get_attribute("class") or ""
    assert active_class in classes


def test_keyboard_0_triggers_no_issues(page: Page):
    reach_eval(page)
    total = progress_label(page).split(" / ")[1]
    page.keyboard.press("0")
    assert progress_label(page) == f"2 / {total}"


def test_keyboard_enter_triggers_save(page: Page):
    reach_eval(page)
    total = progress_label(page).split(" / ")[1]
    page.keyboard.press("Enter")
    assert progress_label(page) == f"2 / {total}"


def test_keyboard_plus_adds_issue(page: Page):
    reach_eval(page)
    page.keyboard.press("M")
    page.keyboard.press("a")
    page.keyboard.press("+")
    assert issue_count(page) == 1


# ── complete screen ───────────────────────────────────────────────────────────

def test_complete_screen_after_all_judged(page: Page):
    reach_eval(page)
    judge_all_no_issues(page)
    page.wait_for_function(
        "() => document.getElementById('complete-screen').classList.contains('active')"
    )
    assert on_screen(page, "complete-screen")


def test_complete_stats_text(page: Page):
    reach_eval(page)
    judge_all_no_issues(page)
    page.wait_for_function(
        "() => document.getElementById('complete-screen').classList.contains('active')"
    )
    assert "items judged" in page.locator("#complete-stats").text_content()


# ── inconsistency review screen ───────────────────────────────────────────────

def test_review_screen_appears_with_inconsistency(page: Page):
    reach_eval(page)
    inject_inconsistency_and_review(page)
    page.wait_for_function(
        "() => document.getElementById('review-screen').classList.contains('active')"
    )
    assert on_screen(page, "review-screen")
    assert "inconsistenc" in page.locator("#review-subtitle").text_content().lower()


def test_review_prev_button_disabled_on_first(page: Page):
    reach_eval(page)
    inject_inconsistency_and_review(page)
    page.wait_for_function(
        "() => document.getElementById('review-screen').classList.contains('active')"
    )
    assert page.locator("#btn-review-prev").is_disabled()


def test_review_finish_button_when_single_inconsistency(page: Page):
    """With exactly one inconsistency the next button reads 'Finish ✓'."""
    reach_eval(page)
    inject_inconsistency_and_review(page)
    page.wait_for_function(
        "() => document.getElementById('review-screen').classList.contains('active')"
    )
    assert page.locator("#btn-review-next").text_content().strip() == "Finish ✓"


def test_review_use_judgment_resolves_to_complete(page: Page):
    reach_eval(page)
    inject_inconsistency_and_review(page)
    page.wait_for_function(
        "() => document.getElementById('review-screen').classList.contains('active')"
    )
    page.locator("[data-use-idx]").first.click()
    page.wait_for_function(
        "() => document.getElementById('complete-screen').classList.contains('active')"
    )
    assert on_screen(page, "complete-screen")


def test_review_re_evaluate_shows_panel(page: Page):
    reach_eval(page)
    inject_inconsistency_and_review(page)
    page.wait_for_function(
        "() => document.getElementById('review-screen').classList.contains('active')"
    )
    page.locator("#btn-re-eval").click()
    assert page.locator("#re-eval-panel").is_visible()


def test_review_re_evaluate_save_resolution_reaches_complete(page: Page):
    """Adding issues in the re-eval panel and saving resolves the inconsistency → complete."""
    reach_eval(page)
    inject_inconsistency_and_review(page)
    page.wait_for_function(
        "() => document.getElementById('review-screen').classList.contains('active')"
    )
    page.locator("#btn-re-eval").click()
    page.locator("#re-sev-group [data-value='minor']").click()
    page.locator("#re-cat-group [data-value='style']").click()
    page.locator("#btn-re-add").click()
    page.locator("#btn-re-save").click()
    page.wait_for_function(
        "() => document.getElementById('complete-screen').classList.contains('active')"
    )
    assert on_screen(page, "complete-screen")


def test_review_re_evaluate_no_issues_reaches_complete(page: Page):
    """Clicking 'No issues' in the re-eval panel resolves with an empty judgment → complete."""
    reach_eval(page)
    inject_inconsistency_and_review(page)
    page.wait_for_function(
        "() => document.getElementById('review-screen').classList.contains('active')"
    )
    page.locator("#btn-re-eval").click()
    page.locator("#btn-re-no-issues").click()
    page.wait_for_function(
        "() => document.getElementById('complete-screen').classList.contains('active')"
    )
    assert on_screen(page, "complete-screen")


# ── complete screen extras ────────────────────────────────────────────────────

def test_complete_evaluate_another_reaches_film_screen(page: Page):
    reach_eval(page)
    judge_all_no_issues(page)
    page.wait_for_function(
        "() => document.getElementById('complete-screen').classList.contains('active')"
    )
    page.locator("#btn-evaluate-another").click()
    page.wait_for_function(
        "() => document.getElementById('film-screen').classList.contains('active')"
    )
    assert on_screen(page, "film-screen")


def test_complete_stats_skipped_count(page: Page):
    """Stats line reports the correct number of skipped items."""
    reach_eval(page)
    page.locator("#btn-skip").click()
    page.locator("#btn-skip").click()
    page.evaluate("""
        () => {
            const skipped = new Set(App.session.skipped);
            App.session.tasks.forEach((t, i) => {
                if (!skipped.has(i))
                    App.session.judgments[String(i)] = { issues: [], viewed_analysis: false };
            });
            saveSession();
            startReview();
        }
    """)
    page.wait_for_function(
        "() => document.getElementById('complete-screen').classList.contains('active')"
    )
    stats = page.locator("#complete-stats").text_content()
    assert "2 skipped" in stats


# ── instructions modal ────────────────────────────────────────────────────────

def test_instructions_modal_opens(page: Page):
    reach_eval(page)
    page.locator("#btn-help").click()
    assert page.locator("#instructions-modal").evaluate(
        "el => el.classList.contains('open')"
    )


def test_instructions_modal_closes(page: Page):
    reach_eval(page)
    page.locator("#btn-help").click()
    page.locator("#btn-modal-close").click()
    assert not page.locator("#instructions-modal").evaluate(
        "el => el.classList.contains('open')"
    )


def test_instructions_modal_closes_on_overlay_click(page: Page):
    """Clicking the overlay (outside the modal box) closes the modal."""
    reach_eval(page)
    page.locator("#btn-help").click()
    # Click the overlay element itself, not the inner box
    page.locator("#instructions-modal").click(position={"x": 5, "y": 5})
    assert not page.locator("#instructions-modal").evaluate(
        "el => el.classList.contains('open')"
    )


# ── context segments content ──────────────────────────────────────────────────

def test_context_button_visible_when_subs_available(page: Page):
    """Show-context button is visible when the film has subtitle data."""
    reach_eval(page)
    assert page.locator("#btn-show-context").is_visible()


def test_context_segments_render_on_toggle(page: Page):
    """Opening the context panel shows at least one subtitle segment."""
    reach_eval(page)
    page.locator("#btn-show-context").click()
    assert page.locator("#context-segments li").count() >= 1


def test_context_current_segment_marked(page: Page):
    """The segment(s) being evaluated are highlighted with the 'current' class."""
    reach_eval(page)
    page.locator("#btn-show-context").click()
    assert page.locator("#context-segments li.current").count() >= 1


def _current_item_seg_range(page: Page) -> tuple[int, int]:
    """Return (min_seg, max_seg) for the current eval item."""
    segs = page.evaluate("""
        () => {
            const { task } = App.navSequence[App.sliderPos - 1];
            const item = App.itemsByFilm[task.film]?.[task.trans_model]?.[task.item_id];
            return item ? item.segment_number : [];
        }
    """)
    return min(segs), max(segs)


def test_context_has_segments_before_current(page: Page):
    """Context window shows subtitle lines that precede the current item."""
    reach_eval(page)
    min_seg, _ = _current_item_seg_range(page)
    page.locator("#btn-show-context").click()
    seg_nums = [
        int(el.text_content())
        for el in page.locator("#context-segments .context-seg-num").all()
    ]
    assert any(n < min_seg for n in seg_nums), \
        f"No segments before current (min={min_seg}), rendered: {seg_nums}"


def test_context_has_segments_after_current(page: Page):
    """Context window shows subtitle lines that follow the current item."""
    reach_eval(page)
    _, max_seg = _current_item_seg_range(page)
    page.locator("#btn-show-context").click()
    seg_nums = [
        int(el.text_content())
        for el in page.locator("#context-segments .context-seg-num").all()
    ]
    assert any(n > max_seg for n in seg_nums), \
        f"No segments after current (max={max_seg}), rendered: {seg_nums}"


# ── auto-fill consensus ───────────────────────────────────────────────────────

def test_autofill_triggers_after_three_identical_judgments(page: Page):
    """When 3+ identical judgments exist for the same text, remaining occurrences are auto-filled."""
    reach_eval(page)
    n_filled = page.evaluate("""
        () => {
            // Inject 4 copies of task 0 into the session so we control the text
            const task0 = App.session.tasks[0];
            const base  = App.session.tasks.length;
            for (let i = 0; i < 4; i++)
                App.session.tasks.push({ ...task0 });
            // Judge the first 3 copies identically (no issues)
            for (let i = 0; i < 3; i++)
                App.session.judgments[String(base + i)] = { issues: [], viewed_analysis: false };
            // base+3 is intentionally left unjudged — should be auto-filled
            saveSession();
            return autoFillFromConsensus();
        }
    """)
    assert n_filled >= 1


def test_autofill_progress_label_shows_auto_count(page: Page):
    """After auto-fill, the progress label includes '· N auto'."""
    reach_eval(page)
    page.evaluate("""
        () => {
            const task0 = App.session.tasks[0];
            const base  = App.session.tasks.length;
            for (let i = 0; i < 4; i++)
                App.session.tasks.push({ ...task0 });
            for (let i = 0; i < 3; i++)
                App.session.judgments[String(base + i)] = { issues: [], viewed_analysis: false };
            saveSession();
            autoFillFromConsensus();
            // Rebuild navSequence to include the new tasks, then re-render
            App.navSequence = App.session.tasks.map((t, i) => ({ taskIdx: i, task: t }));
            App.totalTasks  = App.navSequence.length;
            renderCurrentItem();
        }
    """)
    label = page.locator("#progress-label").text_content().strip()
    assert "auto" in label


def test_autofill_does_not_trigger_below_three(page: Page):
    """Two identical judgments are not enough to trigger auto-fill."""
    reach_eval(page)
    n_filled = page.evaluate("""
        () => {
            const task0 = App.session.tasks[0];
            const base  = App.session.tasks.length;
            for (let i = 0; i < 3; i++)
                App.session.tasks.push({ ...task0 });
            // Only 2 identical judgments
            for (let i = 0; i < 2; i++)
                App.session.judgments[String(base + i)] = { issues: [], viewed_analysis: false };
            saveSession();
            return autoFillFromConsensus();
        }
    """)
    assert n_filled == 0


# ── translation context ───────────────────────────────────────────────────────

def test_trans_context_button_visible_when_data_available(page: Page):
    reach_eval(page)
    # Button is hidden when no translation subs available; visible otherwise
    is_visible = page.locator("#btn-show-trans-context").is_visible()
    has_data = page.evaluate("""
        () => {
            const { task } = App.navSequence[App.sliderPos - 1];
            const subs = (App.transSubsByFilm[task.film] || {})[task.trans_model]?.[task.method];
            return !!subs;
        }
    """)
    assert is_visible == has_data


def test_trans_context_segments_render_when_available(page: Page):
    reach_eval(page)
    if not page.locator("#btn-show-trans-context").is_visible():
        pytest.skip("No translation subtitle data for this item")
    page.locator("#btn-show-trans-context").click()
    assert page.locator("#trans-context-segments li").count() >= 1


def test_trans_context_has_segments_before_and_after(page: Page):
    reach_eval(page)
    if not page.locator("#btn-show-trans-context").is_visible():
        pytest.skip("No translation subtitle data for this item")
    min_seg, max_seg = _current_item_seg_range(page)
    page.locator("#btn-show-trans-context").click()
    seg_nums = [
        int(el.text_content())
        for el in page.locator("#trans-context-segments .context-seg-num").all()
    ]
    assert any(n < min_seg for n in seg_nums), f"No segments before current, got: {seg_nums}"
    assert any(n > max_seg for n in seg_nums), f"No segments after current, got: {seg_nums}"


# ── analysis content ──────────────────────────────────────────────────────────

def test_analysis_text_populated(page: Page):
    """The analysis panel contains actual text when opened."""
    reach_eval(page)
    page.locator("#btn-show-analysis").click()
    assert page.locator("#analysis-text").text_content().strip() != ""


# ── skip all items ────────────────────────────────────────────────────────────

def test_skip_all_items_reaches_complete(page: Page):
    """Skipping every item exhausts the nav sequence and reaches the complete screen."""
    reach_eval(page)
    total = int(page.locator("#progress-label").text_content().strip().split(" / ")[1])
    for _ in range(total):
        btn = page.locator("#btn-skip")
        if not btn.is_visible():
            break
        btn.click()
    page.wait_for_function(
        "() => document.getElementById('complete-screen').classList.contains('active')"
    )
    assert on_screen(page, "complete-screen")


def test_skip_all_stats_show_correct_skipped_count(page: Page):
    reach_eval(page)
    total = int(page.locator("#progress-label").text_content().strip().split(" / ")[1])
    for _ in range(total):
        btn = page.locator("#btn-skip")
        if not btn.is_visible():
            break
        btn.click()
    page.wait_for_function(
        "() => document.getElementById('complete-screen').classList.contains('active')"
    )
    stats = page.locator("#complete-stats").text_content()
    assert f"{total} skipped" in stats
