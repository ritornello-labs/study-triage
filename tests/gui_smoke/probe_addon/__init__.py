from __future__ import annotations

import copy
import importlib
import json
import os
import traceback
from pathlib import Path
from typing import Any

from aqt import gui_hooks, mw
from aqt.qt import QApplication, QMenu, QPoint, QRect, QTimer, Qt, QToolTip

try:
    from aqt.qt import QTest
except ImportError:
    try:
        from PyQt6.QtTest import QTest
    except ImportError:
        from PyQt5.QtTest import QTest


MENU_LABEL = "Study Triage"
SCREENSHOT_DECK_NAME = "Spanish Vocabulary"
SCREENSHOT_NEW_COUNT = 20
SCREENSHOT_DUE_COUNT = 87
EXPECTED_ACTIONS = [
    "Set Today's New Cards to 0",
    "Answer Due Cards as Good",
    "Answer Due Cards as Easy",
]
MEDIA_START_DELAY_MS = int(os.environ.get("ANKI_ADDON_WORKBENCH_MEDIA_START_DELAY_MS", "500"))
MEDIA_MENU_HOLD_MS = int(os.environ.get("ANKI_ADDON_WORKBENCH_MEDIA_MENU_HOLD_MS", "100"))


def _normal_text(text: str) -> str:
    return text.replace("&", "").strip()


def _action_snapshot(menu: QMenu) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for action in menu.actions():
        submenu = action.menu()
        item: dict[str, Any] = {
            "text": _normal_text(action.text()),
            "enabled": bool(action.isEnabled()),
            "separator": bool(action.isSeparator()),
        }
        if submenu is not None:
            item["submenu"] = _action_snapshot(submenu)
        items.append(item)
    return items


def _find_menu(items: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    for item in items:
        if item.get("text") == label and "submenu" in item:
            return item
    return None


def _find_qmenu(menu: QMenu, label: str) -> QMenu:
    for action in menu.actions():
        submenu = action.menu()
        if _normal_text(action.text()) == label and submenu is not None:
            return submenu
    raise AssertionError(f"missing submenu: {label}")


def _find_qaction(menu: QMenu, label: str):
    for action in menu.actions():
        if not action.isSeparator() and _normal_text(action.text()) == label:
            return action
    raise AssertionError(f"missing action: {label}")


def _action_texts(items: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("text", ""))
        for item in items
        if not item.get("separator") and item.get("text")
    ]


def _assert_expected_actions(items: list[dict[str, Any]]) -> None:
    texts = _action_texts(items)
    missing = [label for label in EXPECTED_ACTIONS if label not in texts]
    if missing:
        raise AssertionError(f"missing action(s): {', '.join(missing)}")


def _ensure_smoke_deck_id() -> int:
    assert mw is not None
    assert mw.col is not None
    deck_id = int(mw.col.decks.id("Study Triage GUI Smoke"))
    mw.col.decks.set_current(deck_id)
    return deck_id


def _ensure_screenshot_deck_id() -> int:
    assert mw is not None
    assert mw.col is not None

    deck_id = int(mw.col.decks.id(SCREENSHOT_DECK_NAME))
    card_ids = list(mw.col.find_cards(f'deck:"{SCREENSHOT_DECK_NAME}"'))
    expected_total = SCREENSHOT_NEW_COUNT + SCREENSHOT_DUE_COUNT
    if not card_ids:
        notetype = mw.col.models.current()
        if notetype is None:
            raise AssertionError("could not load the default note type for screenshot setup")
        for index in range(expected_total):
            note = mw.col.new_note(notetype)
            note["Front"] = f"Spanish vocabulary prompt {index + 1}"
            note["Back"] = f"Spanish vocabulary answer {index + 1}"
            mw.col.add_note(note, deck_id)
        card_ids = list(mw.col.find_cards(f'deck:"{SCREENSHOT_DECK_NAME}"'))

    if len(card_ids) != expected_total:
        raise AssertionError(
            f"screenshot story expected {expected_total} cards, found {len(card_ids)}"
        )

    new_card_ids = list(mw.col.find_cards(f'deck:"{SCREENSHOT_DECK_NAME}" is:new'))
    new_card_id_set = set(new_card_ids)
    due_card_ids = [card_id for card_id in card_ids if card_id not in new_card_id_set]
    cards_to_make_due = SCREENSHOT_DUE_COUNT - len(due_card_ids)
    if cards_to_make_due > 0:
        mw.col.sched.set_due_date(new_card_ids[:cards_to_make_due], "0")

    mw.col.decks.set_current(deck_id)
    counts = mw.col.sched.get_queued_cards(fetch_limit=1)
    new_count = int(getattr(counts, "new_count", 0))
    review_count = int(getattr(counts, "review_count", 0))
    if (new_count, review_count) != (SCREENSHOT_NEW_COUNT, SCREENSHOT_DUE_COUNT):
        raise AssertionError(
            "screenshot story should show "
            f"{SCREENSHOT_NEW_COUNT} new / {SCREENSHOT_DUE_COUNT} due, "
            f"got {new_count} new / {review_count} due"
        )

    smoke_deck_id = mw.col.decks.id_for_name("Study Triage GUI Smoke")
    if smoke_deck_id:
        mw.col.decks.remove([smoke_deck_id])

    deck_browser = getattr(mw, "deckBrowser", None)
    refresh = getattr(deck_browser, "refresh", None)
    if callable(refresh):
        rendered = {"done": False}

        def mark_rendered(browser: Any) -> None:
            if browser is deck_browser:
                rendered["done"] = True

        gui_hooks.deck_browser_did_render.append(mark_rendered)
        try:
            refresh()
            for _attempt in range(100):
                _process_events(50)
                if rendered["done"]:
                    break
        finally:
            gui_hooks.deck_browser_did_render.remove(mark_rendered)

        if not rendered["done"]:
            raise AssertionError("deck browser did not render the screenshot story")
        _process_events(250)
    return deck_id


def _qt_left_button():
    return getattr(getattr(Qt, "MouseButton", Qt), "LeftButton")


def _qt_no_modifier():
    return getattr(getattr(Qt, "KeyboardModifier", Qt), "NoModifier")


def _process_events(milliseconds: int = 50) -> None:
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    QTest.qWait(milliseconds)
    if app is not None:
        app.processEvents()


def _click_menu_action(menu: QMenu, action_label: str) -> None:
    action = _find_qaction(menu, action_label)
    menu.adjustSize()
    menu.popup(mw.mapToGlobal(QPoint(80, 80)))
    _process_events(MEDIA_MENU_HOLD_MS)

    rect = menu.actionGeometry(action)
    if not rect.isValid():
        raise AssertionError(f"action has no clickable geometry: {action_label}")

    click_point = rect.center()
    menu.setActiveAction(action)
    QTest.mouseMove(menu, click_point)
    _process_events(50)
    QTest.mouseClick(menu, _qt_left_button(), _qt_no_modifier(), click_point)
    _process_events(150)

    if menu.isVisible():
        menu.hide()
        _process_events(50)


def _run_deck_menu_interaction(deck_id: int) -> dict[str, Any]:
    assert mw is not None
    assert mw.col is not None

    study_triage = importlib.import_module("study_triage")
    setup_limit = 7
    if not study_triage._set_today_new_limit(mw.col, deck_id, setup_limit):
        raise AssertionError("could not set up a nonzero today-only new-card limit")
    if not study_triage._deck_limit_matches(mw.col, deck_id, setup_limit):
        raise AssertionError("smoke deck did not report the setup new-card limit")

    # Reproduce an expired Today-only review limit. Anki deliberately retains
    # the last value with a past day so the UI can offer it as a remembered
    # value, while reporting the override as inactive.
    deck = mw.col.decks.get(deck_id)
    if not isinstance(deck, dict):
        raise AssertionError("could not load smoke deck for stale-limit setup")
    today = int(mw.col.sched.today)
    inactive_day = today - 1 if today > 0 else today + 1
    deck["reviewLimitToday"] = {"limit": 0, "today": inactive_day}
    mw.col.decks.update(deck)
    review_limit_before = copy.deepcopy(deck["reviewLimitToday"])

    limits_before = study_triage._get_backend_deck_limits(mw.col, deck_id)
    if limits_before is None:
        raise AssertionError("could not read smoke deck limits after stale-limit setup")
    if bool(getattr(limits_before, "review_today_active", False)):
        raise AssertionError("stale review limit was unexpectedly active before interaction")
    if int(getattr(limits_before, "review_today")) != 0:
        raise AssertionError("stale review limit did not retain the expected value of 0")

    deck_menu = QMenu(mw)
    gui_hooks.deck_browser_will_show_options_menu(deck_menu, deck_id)
    triage_menu = _find_qmenu(deck_menu, MENU_LABEL)

    triggered = {"count": 0}
    zero_action = _find_qaction(triage_menu, "Set Today's New Cards to 0")
    zero_action.triggered.connect(
        lambda _checked=False: triggered.__setitem__("count", triggered["count"] + 1)
    )

    _click_menu_action(triage_menu, "Set Today's New Cards to 0")

    if triggered["count"] != 1:
        raise AssertionError(
            f"expected one Qt-triggered menu activation, got {triggered['count']}"
        )
    if not study_triage._deck_limit_matches(mw.col, deck_id, 0):
        raise AssertionError("clicked menu action did not set the deck limit to 0")

    limits_after = study_triage._get_backend_deck_limits(mw.col, deck_id)
    if limits_after is None:
        raise AssertionError("could not read smoke deck limits after interaction")
    if bool(getattr(limits_after, "review_today_active", False)):
        raise AssertionError("new-card action reactivated the stale Today-only review limit")
    deck_after = mw.col.decks.get(deck_id)
    if not isinstance(deck_after, dict):
        raise AssertionError("could not reload smoke deck after interaction")
    if deck_after.get("reviewLimitToday") != review_limit_before:
        raise AssertionError("new-card action changed the stored Today-only review limit")

    return {
        "action": "Set Today's New Cards to 0",
        "before_new_today": setup_limit,
        "after_new_today": 0,
        "stale_review_today": 0,
        "review_today_active_after": False,
        "triggered_count": triggered["count"],
        "via": "QTest.mouseClick on deck submenu QMenu action",
    }


def _run_deck_context_menu_interaction(deck_id: int) -> dict[str, Any]:
    assert mw is not None
    assert mw.col is not None

    study_triage = importlib.import_module("study_triage")

    script = study_triage._deck_context_menu_js()
    if "contextmenu" not in script or study_triage.DECK_CONTEXT_MESSAGE_PREFIX not in script:
        raise AssertionError("deck context-menu bridge script is missing expected markers")

    context_menu = study_triage._build_deck_context_menu(deck_id)
    if context_menu is None:
        raise AssertionError("deck context menu builder returned no menu")

    triage_menu = _find_qmenu(context_menu, MENU_LABEL)
    context_menu_items = _action_snapshot(context_menu)
    _assert_expected_actions(_action_snapshot(triage_menu))

    deck_browser = getattr(mw, "deckBrowser", None)
    if deck_browser is None:
        raise AssertionError("main window does not expose deckBrowser")

    calls: list[tuple[Any, int]] = []
    original_show_context_menu = study_triage._show_deck_options_context_menu
    study_triage._show_deck_options_context_menu = (
        lambda context, bridged_deck_id: calls.append((context, bridged_deck_id))
    )
    try:
        handled = study_triage._handle_deck_context_menu_message(
            (False, None),
            f"{study_triage.DECK_CONTEXT_MESSAGE_PREFIX}{deck_id}",
            deck_browser,
        )
    finally:
        study_triage._show_deck_options_context_menu = original_show_context_menu

    if handled != (True, None):
        raise AssertionError(f"deck context-menu bridge was not handled: {handled!r}")
    if calls != [(deck_browser, deck_id)]:
        raise AssertionError(f"deck context-menu bridge called unexpected target: {calls!r}")

    return {
        "bridge_handled": True,
        "deck_id": deck_id,
        "context_menu": context_menu_items,
        "via": "webview JS-message bridge plus deck context submenu builder",
    }


def _run_smoke() -> dict[str, Any]:
    assert mw is not None
    assert mw.col is not None

    tools_menu = mw.form.menuTools
    tools_items = _action_snapshot(tools_menu)
    tools_submenu = _find_menu(tools_items, MENU_LABEL)
    if tools_submenu is None:
        raise AssertionError("Tools menu is missing Study Triage submenu")
    _assert_expected_actions(list(tools_submenu["submenu"]))

    deck_id = _ensure_smoke_deck_id()
    deck_menu = QMenu(mw)
    gui_hooks.deck_browser_will_show_options_menu(deck_menu, deck_id)
    deck_items = _action_snapshot(deck_menu)
    deck_submenu = _find_menu(deck_items, MENU_LABEL)
    if deck_submenu is None:
        raise AssertionError("deck options menu is missing Study Triage submenu")
    _assert_expected_actions(list(deck_submenu["submenu"]))

    zero_action = next(
        (
            item
            for item in deck_submenu["submenu"]
            if item.get("text") == "Set Today's New Cards to 0"
        ),
        None,
    )
    if not zero_action or not zero_action.get("enabled"):
        raise AssertionError("deck-specific zero-new action should be enabled")

    interaction = _run_deck_menu_interaction(deck_id)
    context_interaction = _run_deck_context_menu_interaction(deck_id)

    return {
        "ok": True,
        "tools_menu": tools_items,
        "deck_menu": deck_items,
        "deck_id": deck_id,
        "interaction": interaction,
        "context_interaction": context_interaction,
        "anki_version": getattr(mw, "appVersion", None),
    }


def _write_result(payload: dict[str, Any]) -> None:
    path = os.environ.get("ANKI_ADDON_WORKBENCH_RESULT") or os.environ.get(
        "STUDY_TRIAGE_GUI_SMOKE_RESULT"
    )
    if not path:
        return

    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _save_screenshot() -> str | None:
    path = os.environ.get("ANKI_ADDON_WORKBENCH_SCREENSHOT") or os.environ.get(
        "STUDY_TRIAGE_GUI_SMOKE_SCREENSHOT"
    )
    if not path or mw is None:
        return None

    screenshot_path = Path(path)
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    pixmap = _grab_menu_screenshot()
    if not pixmap.save(str(screenshot_path), "PNG"):
        raise RuntimeError(f"failed to save screenshot to {screenshot_path}")
    return str(screenshot_path)


def _grab_menu_screenshot():
    assert mw is not None
    QToolTip.hideText()
    _hide_transient_widgets()
    _process_events(100)
    deck_id = _ensure_screenshot_deck_id()

    deck_menu = QMenu(mw)
    gui_hooks.deck_browser_will_show_options_menu(deck_menu, deck_id)
    triage_menu = _find_qmenu(deck_menu, MENU_LABEL)
    triage_action = _find_qaction(deck_menu, MENU_LABEL)

    deck_menu.adjustSize()
    anchor = mw.mapToGlobal(QPoint(520, 150))
    deck_menu.popup(anchor)
    _process_events(250)

    triage_rect = deck_menu.actionGeometry(triage_action)
    deck_menu.setActiveAction(triage_action)
    QTest.mouseMove(deck_menu, triage_rect.center())
    _process_events(250)

    triage_menu.adjustSize()
    triage_menu.popup(deck_menu.mapToGlobal(triage_rect.topRight()))
    _process_events(250)
    deck_menu.show()
    deck_menu.raise_()
    triage_menu.raise_()
    _process_events(100)

    try:
        screen = mw.screen() or QApplication.primaryScreen()
        if screen is None:
            return mw.grab()
        bounds = _expanded_bounds(mw.frameGeometry(), deck_menu.frameGeometry(), triage_menu.frameGeometry())
        return screen.grabWindow(0, bounds.x(), bounds.y(), bounds.width(), bounds.height())
    finally:
        triage_menu.hide()
        deck_menu.hide()
        _process_events(50)


def _expanded_bounds(*rects: QRect) -> QRect:
    bounds = QRect(rects[0])
    for rect in rects[1:]:
        bounds = bounds.united(rect)
    return bounds.adjusted(-24, -24, 24, 24)


def _hide_transient_widgets() -> None:
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        if widget is mw or isinstance(widget, QMenu):
            continue
        if widget.isVisible():
            widget.hide()


def _finish() -> None:
    if mw is None:
        return
    mw.unloadProfileAndExit()


def _run_and_quit() -> None:
    try:
        result = _run_smoke()
    except Exception as exc:
        result = {
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }

    try:
        screenshot = _save_screenshot()
        if screenshot:
            result["screenshot"] = screenshot
    except Exception as exc:
        result["screenshot_error"] = str(exc)

    _write_result(result)
    QTimer.singleShot(100, _finish)


def _schedule_smoke() -> None:
    QTimer.singleShot(MEDIA_START_DELAY_MS, _run_and_quit)


gui_hooks.main_window_did_init.append(_schedule_smoke)
