from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from aqt import gui_hooks, mw
    from aqt.utils import askUser, showInfo, tooltip
except Exception:  # pragma: no cover
    gui_hooks = None
    mw = None
    askUser = None
    showInfo = None
    tooltip = None


MENU_LABEL = "Study Triage"
ZERO_NEW_LABEL = "Set Today's New Cards to 0"
ANSWER_DUE_GOOD_LABEL = "Answer Due Cards as Good"
ANSWER_DUE_EASY_LABEL = "Answer Due Cards as Easy"
DECK_CONTEXT_MESSAGE_PREFIX = "study-triage-deck-context:"
EASE_GOOD = 3
EASE_EASY = 4
ANKI_UNDO_ENTRY_LIMIT = 30
UNDO_MERGE_SAFETY_MARGIN = 5
UNDO_MERGE_PREFERRED_INTERVAL = 20

_tools_menu: Optional[Any] = None
_active_deck_context_menu: Optional[Any] = None


class _BulkAnswerResult:
    def __init__(
        self,
        answered: int,
        failed: List[Tuple[int, str]],
        cancelled: bool,
        changes: Any,
        undo_available: bool,
        undo_error: Optional[str],
    ) -> None:
        self.answered = answered
        self.failed = failed
        self.cancelled = cancelled
        self.changes = changes
        self.undo_available = undo_available
        self.undo_error = undo_error


def _setup_menu() -> None:
    global _tools_menu

    if mw is None or _tools_menu is not None:
        return

    tools_menu = getattr(getattr(mw, "form", None), "menuTools", None)
    if tools_menu is None or not hasattr(tools_menu, "addMenu"):
        return

    _tools_menu = tools_menu.addMenu(MENU_LABEL)
    _add_triage_actions(_tools_menu)


def _add_deck_triage_submenu(menu, deck_id: int, *, with_separator: bool = False) -> Any:
    if mw is None or mw.col is None:
        return None

    normalized_deck_id = _normalize_deck_id(deck_id)
    if normalized_deck_id is None:
        return None

    deck = _get_deck(mw.col, normalized_deck_id)
    if not isinstance(deck, dict):
        return None

    if with_separator:
        menu.addSeparator()
    submenu = menu.addMenu(MENU_LABEL)
    _add_triage_actions(submenu, normalized_deck_id)
    return submenu


def _add_deck_options_menu_item(menu, deck_id: int) -> None:
    _add_deck_triage_submenu(menu, deck_id, with_separator=True)


def _build_deck_context_menu(deck_id: int) -> Any:
    if mw is None:
        return None

    try:
        from aqt.qt import QMenu
    except Exception:
        return None

    menu = QMenu(mw)
    if _add_deck_triage_submenu(menu, deck_id) is None:
        return None
    return menu


def _show_study_triage_deck_context_menu(deck_id: int) -> None:
    global _active_deck_context_menu

    menu = _build_deck_context_menu(deck_id)
    if menu is None:
        return

    _active_deck_context_menu = menu

    def clear_active_menu() -> None:
        global _active_deck_context_menu
        if _active_deck_context_menu is menu:
            _active_deck_context_menu = None

    try:
        menu.aboutToHide.connect(clear_active_menu)
    except Exception:
        pass

    try:
        from aqt.qt import QCursor
    except Exception:
        return

    menu.popup(QCursor.pos())


def _deck_context_menu_js() -> str:
    return f"""
<script>
(function() {{
    if (window.studyTriageDeckContextInstalled) {{
        return;
    }}
    window.studyTriageDeckContextInstalled = true;

    function deckIdFromTarget(target) {{
        if (!target || !target.closest) {{
            return null;
        }}

        var link = target.closest("a");
        if (link) {{
            var onclick = link.getAttribute("onclick") || "";
            var match = onclick.match(/open:(\\d+)/);
            if (match) {{
                return match[1];
            }}
        }}

        var deckCell = target.closest("td.decktd");
        if (deckCell) {{
            var row = deckCell.closest("tr[id]");
            if (row && /^\\d+$/.test(row.id)) {{
                return row.id;
            }}
        }}

        return null;
    }}

    document.addEventListener("contextmenu", function(event) {{
        var deckId = deckIdFromTarget(event.target);
        if (!deckId || typeof pycmd !== "function") {{
            return;
        }}

        event.preventDefault();
        event.stopPropagation();
        pycmd("{DECK_CONTEXT_MESSAGE_PREFIX}" + deckId);
    }}, true);
}})();
</script>
"""


def _is_deck_browser_context(context: Any) -> bool:
    if context is None:
        return False

    try:
        from aqt.deckbrowser import DeckBrowser
    except Exception:
        return context.__class__.__name__ == "DeckBrowser"

    return isinstance(context, DeckBrowser)


def _inject_deck_context_menu_js(web_content: Any, context: Any) -> None:
    if _is_deck_browser_context(context):
        web_content.body += _deck_context_menu_js()


def _parse_deck_context_menu_message(message: str) -> Optional[int]:
    if not message.startswith(DECK_CONTEXT_MESSAGE_PREFIX):
        return None

    raw_deck_id = message[len(DECK_CONTEXT_MESSAGE_PREFIX) :]
    if not raw_deck_id.isdigit():
        return None

    return int(raw_deck_id)


def _show_deck_options_context_menu(context: Any, deck_id: int) -> None:
    if mw is None or mw.col is None:
        return

    normalized_deck_id = _normalize_deck_id(deck_id)
    if normalized_deck_id is None:
        return

    deck = _get_deck(mw.col, normalized_deck_id)
    if not isinstance(deck, dict):
        return

    show_options = getattr(context, "_showOptions", None)
    if callable(show_options):
        show_options(str(normalized_deck_id))
        return

    _show_study_triage_deck_context_menu(normalized_deck_id)


def _message_already_handled(handled: Any) -> bool:
    if isinstance(handled, tuple):
        return bool(handled[0])
    return bool(handled)


def _handled_js_message_result(handled: Any) -> Any:
    if isinstance(handled, tuple):
        return True, None
    return True


def _handle_deck_context_menu_message(handled: Any, message: str, context: Any) -> Any:
    if _message_already_handled(handled) or not _is_deck_browser_context(context):
        return handled

    deck_id = _parse_deck_context_menu_message(message)
    if deck_id is None:
        return handled

    _show_deck_options_context_menu(context, deck_id)
    return _handled_js_message_result(handled)


def _add_triage_actions(menu, deck_id: Optional[int] = None) -> None:
    zero_action = menu.addAction(ZERO_NEW_LABEL)
    if deck_id is None:
        zero_action.triggered.connect(
            lambda _checked=False: _run_action(
                ZERO_NEW_LABEL,
                _zero_today_new_cards,
            )
        )
    elif _is_regular_deck(mw.col, deck_id):
        zero_action.triggered.connect(
            lambda _checked=False, deck_id=deck_id: _run_action(
                ZERO_NEW_LABEL,
                lambda: _zero_today_new_cards_for_deck(deck_id),
            )
        )
    else:
        zero_action.setEnabled(False)
        try:
            zero_action.setToolTip("Today-only new-card limits apply to regular decks.")
        except Exception:
            pass

    menu.addSeparator()
    _add_menu_action(
        menu,
        ANSWER_DUE_GOOD_LABEL,
        lambda: _answer_due_cards(EASE_GOOD, "Good", deck_id),
    )
    _add_menu_action(
        menu,
        ANSWER_DUE_EASY_LABEL,
        lambda: _answer_due_cards(EASE_EASY, "Easy", deck_id),
    )


def _add_menu_action(menu, label: str, callback) -> None:
    action = menu.addAction(label)
    if action is not None:
        action.triggered.connect(lambda _checked=False: _run_action(label, callback))


def _run_action(label: str, callback) -> None:
    try:
        callback()
    except Exception as exc:
        _log_exception(f"Action failed: {label}", exc)
        if showInfo is not None:
            showInfo(f"{label} failed:\n\n{exc}", parent=mw)


def _zero_today_new_cards() -> None:
    if mw is None or mw.col is None:
        return

    if askUser is not None:
        confirmed = askUser(
            "Set 'Today only' new cards/day to 0 for every regular deck in this collection?\n\n"
            "This only affects today and will reset automatically tomorrow.",
            parent=mw,
        )
        if not confirmed:
            return

    targets = _collect_target_decks(mw.col)
    if not targets:
        if showInfo is not None:
            showInfo("No regular decks were found in this collection.", parent=mw)
        return

    changed, failed, undo_available, undo_error = _set_today_new_limit_for_targets(
        mw.col,
        targets,
        0,
    )

    _refresh_main_window()

    if failed and showInfo is not None:
        details = "\n".join(failed[:15])
        more = ""
        if len(failed) > 15:
            more = f"\n...and {len(failed) - 15} more."
        showInfo(
            f"Set today's new-card limit to 0 for {len(changed)} deck(s), "
            f"but failed on {len(failed)} deck(s):\n\n{details}{more}",
            parent=mw,
        )
        return

    if undo_error:
        _log_message(
            "Undo grouping issue after setting new-card limits",
            undo_error,
        )
        if showInfo is not None:
            showInfo(
                f"Set today's new-card limit to 0 for {len(changed)} deck(s), "
                f"but undo was not grouped:\n\n{undo_error}",
                parent=mw,
            )
            return

    if tooltip is not None:
        undo_suffix = " Use Edit > Undo to reverse." if undo_available else ""
        tooltip(
            f"Set Today only new/day = 0 for {len(changed)} deck(s).{undo_suffix}",
            parent=mw,
            period=4000,
        )


def _set_today_new_limit_for_targets(
    col,
    targets: List[Tuple[int, str]],
    limit: int,
) -> Tuple[List[str], List[str], bool, Optional[str]]:
    custom_undo_target = _add_custom_undo_entry(
        col, "Study Triage: Set Today's New Cards to 0"
    )
    changed: List[str] = []
    failed: List[str] = []
    changes = _empty_op_changes()
    merge_interval = _undo_merge_interval(len(targets))
    changes_since_undo_merge = 0

    for index, (deck_id, name) in enumerate(targets, start=1):
        if _set_today_new_limit(col, deck_id, limit):
            changed.append(name)
            changes_since_undo_merge += 1
            if (
                custom_undo_target is not None
                and changes_since_undo_merge >= merge_interval
                and index < len(targets)
            ):
                changes = _merge_undo_entries_during_batch(
                    col,
                    custom_undo_target,
                    changes,
                    "Undo grouping issue while setting new-card limits",
                )
                changes_since_undo_merge = 0
        else:
            failed.append(name)

    if not changed:
        _cleanup_unanswered_custom_undo_entry(col, custom_undo_target, changes)
        return (changed, failed, False, None)

    changes, undo_available, undo_error = _finalize_custom_undo_entries(
        col,
        custom_undo_target,
        len(changed),
        changes,
        "custom undo entry unavailable",
    )
    return (changed, failed, undo_available, undo_error)


def _zero_today_new_cards_for_deck(deck_id: int) -> None:
    if mw is None or mw.col is None:
        return

    deck = _get_deck(mw.col, deck_id)
    if not isinstance(deck, dict) or bool(deck.get("dyn")):
        if showInfo is not None:
            showInfo("This action is only available for regular decks.", parent=mw)
        return

    deck_name = str(deck.get("name") or deck_id)
    if not _set_today_new_limit(mw.col, deck_id, 0):
        if showInfo is not None:
            showInfo(
                f"Could not set Today only new/day = 0 for {deck_name}.",
                parent=mw,
            )
        return

    _refresh_main_window()

    if tooltip is not None:
        tooltip(
            f"Set Today only new/day = 0 for {deck_name}.",
            parent=mw,
            period=4000,
        )


def _answer_due_cards(ease: int, ease_label: str, deck_id: Optional[int] = None) -> None:
    if mw is None or mw.col is None:
        return

    deck_id = _normalize_deck_id(deck_id)
    query = _due_cards_query(mw.col, deck_id)
    if query is None:
        if showInfo is not None:
            showInfo("Could not find that deck.", parent=mw)
        return

    scope_label = _scope_label(mw.col, deck_id)
    if deck_id is not None and _should_use_scheduler_deck_queue(mw.col, deck_id):
        try:
            card_ids = _prepare_scheduler_deck_due_cards(mw.col, deck_id)
        except Exception as exc:
            _show_operation_error("Could not read Anki's scheduler queue", exc)
            return

        _confirm_and_answer_due_cards(
            card_ids,
            ease,
            ease_label,
            scope_label,
            deck_id,
        )
        return

    try:
        card_ids = _find_due_card_ids(mw.col, query, deck_id)
    except Exception as exc:
        _show_operation_error("Could not search for due cards", exc)
        return

    _confirm_and_answer_due_cards(card_ids, ease, ease_label, scope_label, deck_id)


def _confirm_and_answer_due_cards(
    card_ids: List[int],
    ease: int,
    ease_label: str,
    scope_label: str,
    deck_id: Optional[int],
    custom_undo_target: Optional[int] = None,
) -> None:
    if mw is None:
        return

    if not card_ids:
        _cleanup_unanswered_custom_undo_entry(
            getattr(mw, "col", None),
            custom_undo_target,
            _empty_op_changes(),
        )
        if showInfo is not None:
            showInfo(
                f"No due, unburied review or learning cards found in {scope_label}.",
                parent=mw,
            )
        return

    if not _confirm_bulk_answer_count(
        len(card_ids), ease_label, scope_label, deck_id
    ):
        _cleanup_unanswered_custom_undo_entry(
            getattr(mw, "col", None),
            custom_undo_target,
            _empty_op_changes(),
        )
        return

    if _start_answer_due_cards_operation(
        card_ids, ease, ease_label, scope_label, custom_undo_target
    ):
        return

    _answer_due_cards_synchronously(
        card_ids, ease, ease_label, scope_label, custom_undo_target
    )


def _confirm_bulk_answer_count(
    card_count: int,
    ease_label: str,
    scope_label: str,
    deck_id: Optional[int],
) -> bool:
    custom_response = _show_bulk_answer_confirmation_dialog(
        card_count,
        ease_label,
        scope_label,
        deck_id,
    )
    if custom_response is not None:
        return custom_response

    if askUser is None:
        return True

    scope_line = f"Scope: {scope_label}"
    if deck_id is not None:
        scope_line += " and its subdecks"

    message = (
        f"Answer {card_count} due card(s) as {ease_label}?\n\n"
        f"{scope_line}\n"
        "Included: due review and learning cards only\n"
        "Excluded: new cards\n\n"
        "This reschedules each card as if you reviewed it and chose "
        f"{ease_label}. Already-answered cards remain changed if the operation "
        "is interrupted, but the add-on will try to group the batch into one "
        "Anki undo step."
    )

    try:
        return bool(
            askUser(
                message,
                parent=mw,
                title=f"Study Triage: Answer as {ease_label}",
                defaultno=True,
            )
        )
    except TypeError:
        return bool(askUser(message, parent=mw))


def _show_bulk_answer_confirmation_dialog(
    card_count: int,
    ease_label: str,
    scope_label: str,
    deck_id: Optional[int],
) -> Optional[bool]:
    try:
        from html import escape

        from aqt.qt import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
    except Exception:
        return None

    dialog = QDialog(mw)
    dialog.setWindowTitle(f"Study Triage: Answer as {ease_label}")
    dialog.setMinimumWidth(460)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(12)

    title = QLabel(f"Answer {_plural(card_count, 'due card')} as {ease_label}?")
    title.setWordWrap(True)
    title.setStyleSheet("font-size: 17px; font-weight: 600;")
    layout.addWidget(title)

    scope = escape(scope_label)
    if deck_id is not None:
        scope += " and its subdecks"
    body = QLabel(
        "<p>"
        f"<b>Scope:</b> {scope}<br>"
        f"<b>Included:</b> {_included_cards_label(deck_id)}<br>"
        f"<b>Excluded:</b> {_excluded_cards_label(deck_id)}"
        "</p>"
        "<p>This reschedules the cards as if you reviewed them.</p>"
    )
    body.setWordWrap(True)
    _set_selectable_text(body)
    layout.addWidget(body)

    buttons = QHBoxLayout()
    buttons.addStretch(1)
    cancel_button = QPushButton("Cancel")
    answer_button = QPushButton(f"Answer as {ease_label}")
    cancel_button.setDefault(True)
    answer_button.setAutoDefault(False)
    cancel_button.clicked.connect(dialog.reject)
    answer_button.clicked.connect(dialog.accept)
    buttons.addWidget(cancel_button)
    buttons.addWidget(answer_button)
    layout.addLayout(buttons)

    return _exec_dialog(dialog) == 1


def _show_bulk_answer_result_dialog(
    result: _BulkAnswerResult,
    ease_label: str,
    scope_label: str,
) -> bool:
    try:
        from html import escape

        from aqt.qt import (
            QDialog,
            QHBoxLayout,
            QLabel,
            QPlainTextEdit,
            QPushButton,
            QVBoxLayout,
        )
    except Exception:
        return False

    dialog = QDialog(mw)
    dialog.setWindowTitle("Study Triage")
    dialog.setMinimumWidth(520)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(12)

    title_text = f"Answered {_plural(result.answered, 'due card')} as {ease_label}"
    if result.cancelled:
        title_text = f"Stopped after answering {_plural(result.answered, 'due card')}"
    title = QLabel(title_text)
    title.setWordWrap(True)
    title.setStyleSheet("font-size: 17px; font-weight: 600;")
    layout.addWidget(title)

    status_parts = [
        f"<b>Scope:</b> {escape(scope_label)}",
    ]
    if result.failed:
        status_parts.append(f"<b>Failed:</b> {_plural(len(result.failed), 'card')}")
    if result.undo_available:
        status_parts.append("<b>Undo:</b> Edit > Undo reverses this batch")
    elif result.undo_error:
        status_parts.append(f"<b>Undo:</b> not grouped ({escape(result.undo_error)})")
    else:
        status_parts.append("<b>Undo:</b> not exposed as a single batch")

    body = QLabel("<br>".join(status_parts))
    body.setWordWrap(True)
    _set_selectable_text(body)
    layout.addWidget(body)

    if result.failed:
        details_label = QLabel("Failed card details")
        details_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(details_label)

        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(_failed_card_details(result.failed))
        details.setMinimumHeight(86)
        details.setMaximumHeight(160)
        layout.addWidget(details)

    buttons = QHBoxLayout()
    if result.failed:
        browse_button = QPushButton("Open Failed Cards")
        browse_button.clicked.connect(
            lambda _checked=False: _open_failed_cards(result.failed)
        )
        buttons.addWidget(browse_button)

    buttons.addStretch(1)
    ok_button = QPushButton("OK")
    ok_button.setDefault(True)
    ok_button.clicked.connect(dialog.accept)
    buttons.addWidget(ok_button)
    layout.addLayout(buttons)

    _exec_dialog(dialog)
    return True


def _failed_card_details(failed: List[Tuple[int, str]]) -> str:
    lines = []
    for card_id, reason in failed:
        detail = reason or "unknown error"
        lines.append(f"{card_id}: {detail}")
    return "\n".join(lines)


def _open_failed_cards(failed: List[Tuple[int, str]]) -> None:
    card_ids = [card_id for card_id, _reason in failed]
    if not card_ids:
        return

    query = " OR ".join(f"cid:{int(card_id)}" for card_id in card_ids)
    try:
        import aqt

        aqt.dialogs.open("Browser", mw, search=(query,))
    except Exception as exc:
        _show_operation_error("Could not open failed cards", exc)


def _plural(count: int, singular: str) -> str:
    suffix = "" if count == 1 else "s"
    return f"{count} {singular}{suffix}"


def _set_selectable_text(label) -> None:
    try:
        from aqt.qt import Qt

        try:
            flags = (
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
        except AttributeError:
            flags = Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        label.setTextInteractionFlags(flags)
    except Exception:
        pass


def _exec_dialog(dialog) -> int:
    run = getattr(dialog, "exec", None)
    if callable(run):
        return int(run())

    run = getattr(dialog, "exec_", None)
    if callable(run):
        return int(run())

    return 0


def _start_answer_due_cards_operation(
    card_ids: List[int],
    ease: int,
    ease_label: str,
    scope_label: str,
    custom_undo_target: Optional[int] = None,
) -> bool:
    if mw is None:
        return False

    try:
        from aqt.operations import CollectionOp
    except Exception:
        return False

    progress_label = f"Answering due cards as {ease_label}..."
    try:
        (
            CollectionOp(
                parent=mw,
                op=lambda col: _answer_due_cards_operation(
                    col, card_ids, ease, progress_label, custom_undo_target
                ),
            )
            .success(
                lambda result: _show_bulk_answer_result(
                    result, ease_label, scope_label
                )
            )
            .failure(
                lambda exc: _show_operation_error(
                    f"Could not answer due cards as {ease_label}", exc
                )
            )
            .run_in_background()
        )
        return True
    except Exception:
        return False


def _answer_due_cards_operation(
    col,
    card_ids: List[int],
    ease: int,
    progress_label: str,
    custom_undo_target: Optional[int] = None,
):
    if custom_undo_target is None:
        custom_undo_target = _add_custom_undo_entry(
            col, "Study Triage: Answer Due Cards"
        )
    answered, failed, cancelled, changes, undo_target = _answer_card_ids_with_progress(
        col,
        card_ids,
        ease,
        progress_label,
        background=True,
        merge_undo_target=custom_undo_target,
    )
    if answered <= 0:
        changes = _cleanup_unanswered_custom_undo_entry(
            col, custom_undo_target, changes
        )
    changes, undo_available, undo_error = _finalize_answer_undo_entries_with_fallback(
        col,
        custom_undo_target or undo_target,
        undo_target,
        answered,
        changes,
        force_merge=custom_undo_target is not None,
    )
    return _BulkAnswerResult(
        answered=answered,
        failed=failed,
        cancelled=cancelled,
        changes=changes,
        undo_available=undo_available,
        undo_error=undo_error,
    )


def _answer_due_cards_synchronously(
    card_ids: List[int],
    ease: int,
    ease_label: str,
    scope_label: str,
    custom_undo_target: Optional[int] = None,
) -> None:
    if mw is None or mw.col is None:
        return

    if custom_undo_target is None:
        custom_undo_target = _add_custom_undo_entry(
            mw.col, "Study Triage: Answer Due Cards"
        )
    answered, failed, cancelled, changes, undo_target = _answer_card_ids_with_progress(
        mw.col,
        card_ids,
        ease,
        f"Answering due cards as {ease_label}...",
        background=False,
        merge_undo_target=custom_undo_target,
    )
    if answered <= 0:
        changes = _cleanup_unanswered_custom_undo_entry(
            mw.col, custom_undo_target, changes
        )
    changes, undo_available, undo_error = _finalize_answer_undo_entries_with_fallback(
        mw.col,
        custom_undo_target or undo_target,
        undo_target,
        answered,
        changes,
        force_merge=custom_undo_target is not None,
    )
    _refresh_main_window()
    result = _BulkAnswerResult(
        answered=answered,
        failed=failed,
        cancelled=cancelled,
        changes=changes,
        undo_available=undo_available,
        undo_error=undo_error,
    )
    _show_bulk_answer_result(result, ease_label, scope_label)


def _show_bulk_answer_result(result, ease_label: str, scope_label: str) -> None:
    _refresh_main_window()

    if result.failed:
        _log_message(
            f"Failed to answer {len(result.failed)} card(s) as {ease_label} in {scope_label}",
            _failed_card_details(result.failed),
        )
    if result.undo_error:
        _log_message(
            f"Undo grouping issue after answering cards as {ease_label} in {scope_label}",
            result.undo_error,
        )

    if result.cancelled or result.failed or not result.undo_available:
        if _show_bulk_answer_result_dialog(result, ease_label, scope_label):
            return

    if result.cancelled and showInfo is not None:
        message = (
            f"Stopped after answering {result.answered} due card(s) as {ease_label} "
            f"in {scope_label}."
        )
        if result.failed:
            message += f"\n\n{len(result.failed)} card(s) failed before stopping."
        message += _undo_note(result)
        showInfo(message, parent=mw)
        return

    if result.failed and showInfo is not None:
        details = "\n".join(
            f"{card_id}: {reason or 'unknown error'}"
            for card_id, reason in result.failed[:20]
        )
        more = ""
        if len(result.failed) > 20:
            more = f"\n...and {len(result.failed) - 20} more."
        showInfo(
            f"Answered {result.answered} due card(s) as {ease_label} in {scope_label}, "
            f"but failed on {len(result.failed)} card(s):\n\n{details}{more}"
            f"{_undo_note(result)}",
            parent=mw,
        )
        return

    if not result.undo_available and showInfo is not None:
        showInfo(
            f"Answered {result.answered} due card(s) as {ease_label} in {scope_label}."
            f"{_undo_note(result)}",
            parent=mw,
        )
        return

    if tooltip is not None:
        tooltip(
            f"Answered {result.answered} due card(s) as {ease_label} in {scope_label}.",
            parent=mw,
            period=5000,
        )


def _undo_note(result) -> str:
    if result.undo_available:
        return "\n\nUse Edit > Undo to reverse this batch."
    if result.undo_error:
        return (
            "\n\nAnki did not expose this as a single undo step. "
            f"Undo grouping detail: {result.undo_error}"
        )
    return "\n\nAnki did not expose this as a single undo step."


def _answer_card_ids_with_progress(
    col,
    card_ids: List[int],
    ease: int,
    progress_label: str,
    background: bool,
    merge_undo_target: Optional[int] = None,
) -> Tuple[int, List[Tuple[int, str]], bool, Any, Optional[int]]:
    failed: List[Tuple[int, str]] = []
    answered = 0
    cancelled = False
    changes = _empty_op_changes()
    undo_target: Optional[int] = None
    active_merge_target = merge_undo_target
    merge_interval = _undo_merge_interval(len(card_ids))
    answers_since_undo_merge = 0
    total = len(card_ids)
    last_update = 0.0

    if not background:
        _progress_start(progress_label, total)
    try:
        native_grade_available, native_changes = _grade_card_ids_natively(
            col, card_ids, ease
        )
        if native_grade_available:
            _progress_update_for_mode(
                progress_label,
                total,
                total,
                background=background,
            )
            changes = _merge_op_changes(changes, native_changes)
            return total, failed, cancelled, changes, _last_undo_step(col)

        for index, card_id in enumerate(card_ids, start=1):
            if _progress_cancel_requested():
                cancelled = True
                break

            now = time.time()
            if index == 1 or index == total or now - last_update >= 0.1:
                _progress_update_for_mode(
                    progress_label,
                    index,
                    total,
                    background=background,
                )
                last_update = now

            ok, reason, card_changes = _answer_card(col, card_id, ease)
            if ok:
                answered += 1
                answers_since_undo_merge += 1
                changes = _merge_op_changes(changes, card_changes)
                if undo_target is None:
                    undo_target = _last_undo_step(col)
                    if active_merge_target is None:
                        active_merge_target = undo_target
                if (
                    active_merge_target is not None
                    and answers_since_undo_merge >= merge_interval
                    and index < total
                ):
                    changes = _merge_undo_entries_during_batch(
                        col,
                        active_merge_target,
                        changes,
                        "Undo grouping issue while answering cards",
                    )
                    answers_since_undo_merge = 0
            else:
                failed.append((card_id, reason))
    finally:
        if not background:
            _progress_finish()

    return answered, failed, cancelled, changes, undo_target


def _grade_card_ids_natively(
    col,
    card_ids: List[int],
    ease: int,
) -> Tuple[bool, Any]:
    backend = getattr(col, "_backend", None)
    grade_now = getattr(backend, "grade_now", None)
    if not callable(grade_now):
        return (False, None)

    # CardAnswer.Rating uses zero-based values in answer-button order:
    # Again, Hard, Good, Easy.  Unlike answerCard(), grade_now() is designed
    # for arbitrary selected card IDs, so it does not require each card to be
    # at the top of the live reviewer queue.
    rating = int(ease) - 1
    if rating not in (0, 1, 2, 3):
        raise ValueError(f"invalid ease: {ease}")

    changes = grade_now(card_ids=[int(card_id) for card_id in card_ids], rating=rating)
    return (True, changes)


def _answer_card(col, card_id: int, ease: int) -> Tuple[bool, str, Any]:
    sched = getattr(col, "sched", None)
    if sched is None:
        return (False, "scheduler unavailable", None)

    card = _get_card(col, card_id)
    if card is None:
        return (False, "card unavailable", None)

    try:
        start_timer = getattr(card, "start_timer", None)
        if callable(start_timer):
            start_timer()
        elif hasattr(card, "timerStarted"):
            card.timerStarted = time.time()

        answer_card = getattr(sched, "answerCard", None)
        if callable(answer_card):
            changes = answer_card(card, int(ease))
            return (True, "", changes)

        answer_card = getattr(sched, "answer_card", None)
        if callable(answer_card):
            changes = answer_card(card, int(ease))
            return (True, "", changes)
    except Exception as exc:
        return (False, str(exc) or exc.__class__.__name__, None)

    return (False, "answerCard API unavailable", None)


def _get_card(col, card_id: int) -> Any:
    for method_name in ("get_card", "getCard"):
        method = getattr(col, method_name, None)
        if not callable(method):
            continue
        try:
            return method(int(card_id))
        except Exception:
            pass

    try:
        from anki.cards import Card

        return Card(col, int(card_id))
    except Exception:
        return None


def _find_card_ids(col, query: str) -> List[int]:
    last_error: Optional[Exception] = None
    for method_name in ("find_cards", "findCards"):
        method = getattr(col, method_name, None)
        if not callable(method):
            continue
        try:
            return [int(card_id) for card_id in method(query)]
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise RuntimeError("No Anki card search API is available.")


def _find_due_card_ids(
    col,
    fallback_query: str,
    deck_id: Optional[int],
) -> List[int]:
    card_ids = _find_card_ids(col, fallback_query)
    return _filter_to_current_deck_cards(col, card_ids, deck_id)


def _should_use_scheduler_deck_queue(col, deck_id: int) -> bool:
    sched = getattr(col, "sched", None)
    if not _scheduler_queue_available(sched):
        return False

    return isinstance(_get_deck(col, deck_id), dict)


def _scheduler_queue_available(sched) -> bool:
    return callable(getattr(sched, "get_queued_cards", None))


def _current_scheduler_deck_id(col) -> Optional[int]:
    decks = getattr(col, "decks", None)
    get_current_id = getattr(decks, "get_current_id", None)
    if not callable(get_current_id):
        return None

    try:
        return int(get_current_id())
    except Exception:
        return None


def _queued_due_card_ids(col) -> List[int]:
    queued = _get_queued_cards(col, 1)
    fetch_limit = _queued_total_count(queued)
    if fetch_limit <= 0:
        return []

    queued = _get_queued_cards(col, fetch_limit)
    return _due_card_ids_from_queued(queued)


def _prepare_scheduler_deck_due_cards(
    col,
    deck_id: int,
) -> List[int]:
    _set_current_deck_for_scheduler_queue(col, deck_id)
    return _queued_due_card_ids(col)


def _set_current_deck_for_scheduler_queue(col, deck_id: int) -> Any:
    if _current_scheduler_deck_id(col) == int(deck_id):
        return _empty_op_changes()

    set_current = getattr(getattr(col, "decks", None), "set_current", None)
    if not callable(set_current):
        return _empty_op_changes()

    try:
        return _changes_from_result(set_current(int(deck_id)))
    except Exception:
        return _empty_op_changes()


def _get_queued_cards(col, fetch_limit: int):
    get_queued_cards = getattr(getattr(col, "sched", None), "get_queued_cards", None)
    if not callable(get_queued_cards):
        raise RuntimeError("No Anki scheduler queue API is available.")

    try:
        return get_queued_cards(fetch_limit=int(fetch_limit))
    except TypeError:
        return get_queued_cards()


def _queued_total_count(queued) -> int:
    return (
        int(getattr(queued, "new_count", 0))
        + int(getattr(queued, "learning_count", 0))
        + int(getattr(queued, "review_count", 0))
    )


def _due_card_ids_from_queued(queued) -> List[int]:
    review_queue = _queued_review_value()
    learning_queue = _queued_learning_value()
    card_ids: List[int] = []
    for queued_card in getattr(queued, "cards", []):
        if int(getattr(queued_card, "queue", -1)) not in (learning_queue, review_queue):
            continue

        card = getattr(queued_card, "card", None)
        try:
            card_ids.append(int(getattr(card, "id")))
        except Exception:
            continue

    return card_ids


def _queued_learning_value() -> int:
    try:
        from anki.scheduler.v3 import QueuedCards

        return int(QueuedCards.LEARNING)
    except Exception:
        return 1


def _queued_review_value() -> int:
    try:
        from anki.scheduler.v3 import QueuedCards

        return int(QueuedCards.REVIEW)
    except Exception:
        return 2


def _filter_to_current_deck_cards(
    col,
    card_ids: List[int],
    deck_id: Optional[int],
) -> List[int]:
    if deck_id is None:
        return card_ids

    current_deck_ids = _current_deck_ids(col, deck_id)
    if not current_deck_ids:
        return []

    filtered: List[int] = []
    for card_id in card_ids:
        card = _get_card(col, card_id)
        try:
            current_deck_id = int(getattr(card, "did"))
        except Exception:
            continue

        if current_deck_id in current_deck_ids:
            filtered.append(card_id)

    return filtered


def _current_deck_ids(col, deck_id: int) -> set:
    deck = _get_deck(col, deck_id)
    if not isinstance(deck, dict):
        return set()

    if bool(deck.get("dyn")):
        return {int(deck_id)}

    deck_name = str(deck.get("name") or "")
    if not deck_name:
        return {int(deck_id)}

    prefix = f"{deck_name}::"
    ids = set()
    for candidate_id, candidate_name in _all_deck_ids_and_names(col):
        if candidate_name != deck_name and not candidate_name.startswith(prefix):
            continue

        candidate = _get_deck(col, candidate_id)
        if isinstance(candidate, dict) and not bool(candidate.get("dyn")):
            ids.add(candidate_id)

    return ids or {int(deck_id)}


def _all_deck_ids_and_names(col) -> List[Tuple[int, str]]:
    decks = getattr(col, "decks", None)
    if decks is None:
        return []

    entries: List[object] = []
    all_names_and_ids = getattr(decks, "all_names_and_ids", None)
    if callable(all_names_and_ids):
        try:
            entries = list(all_names_and_ids())
        except Exception:
            entries = []

    if not entries:
        all_decks = getattr(decks, "all", None)
        if callable(all_decks):
            try:
                entries = list(all_decks())
            except Exception:
                entries = []

    collected: List[Tuple[int, str]] = []
    seen_ids = set()
    for entry in entries:
        name, candidate_id = _deck_name_and_id(entry)
        if name is None or candidate_id is None or candidate_id in seen_ids:
            continue

        seen_ids.add(candidate_id)
        collected.append((candidate_id, name))

    return collected


def _show_operation_error(title: str, exc: Exception) -> None:
    _log_exception(title, exc)
    if showInfo is not None:
        showInfo(f"{title}:\n\n{exc}", parent=mw)


def _log_exception(label: str, exc: Exception) -> None:
    try:
        import traceback

        _log_message(label, "".join(traceback.format_exception(exc)))
    except Exception:
        pass


def _log_message(label: str, details: str) -> None:
    try:
        from pathlib import Path

        path = Path(__file__).resolve().parent / "user_files" / "study-triage.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {label}\n")
            if details:
                handle.write(details.rstrip())
                handle.write("\n")
            handle.write("\n")
    except Exception:
        pass


def _undo_merge_interval(card_count: int) -> int:
    safe_window = max(1, ANKI_UNDO_ENTRY_LIMIT - UNDO_MERGE_SAFETY_MARGIN)
    preferred = max(1, min(UNDO_MERGE_PREFERRED_INTERVAL, safe_window))
    if card_count <= safe_window:
        return max(1, card_count)

    return preferred


def _merge_undo_entries_during_batch(
    col,
    undo_target: int,
    changes: Any,
    error_label: str,
) -> Any:
    merge_undo_entries = getattr(col, "merge_undo_entries", None)
    if not callable(merge_undo_entries):
        return changes

    try:
        merged = merge_undo_entries(undo_target)
        return _merge_op_changes(changes, _changes_from_result(merged))
    except Exception as exc:
        _log_message(
            error_label,
            str(exc) or exc.__class__.__name__,
        )
        return changes


def _finalize_answer_undo_entries(
    col,
    undo_target: Optional[int],
    answered: int,
    changes: Any,
    force_merge: bool = False,
) -> Tuple[Any, bool, Optional[str]]:
    if answered <= 0:
        return (changes, False, None)

    if undo_target is None:
        return (changes, False, "answer operation did not expose an undo step")

    if answered == 1 and not force_merge:
        return (changes, True, None)

    merge_undo_entries = getattr(col, "merge_undo_entries", None)
    if not callable(merge_undo_entries):
        return (changes, False, "merge_undo_entries() is unavailable")

    try:
        merged = merge_undo_entries(undo_target)
        return (_merge_op_changes(changes, _changes_from_result(merged)), True, None)
    except Exception as exc:
        return (changes, False, str(exc) or exc.__class__.__name__)


def _finalize_custom_undo_entries(
    col,
    undo_target: Optional[int],
    changed_count: int,
    changes: Any,
    missing_target_error: str,
) -> Tuple[Any, bool, Optional[str]]:
    if changed_count <= 0:
        changes = _cleanup_unanswered_custom_undo_entry(col, undo_target, changes)
        return (changes, False, None)

    if undo_target is None:
        undo_available = changed_count == 1
        undo_error = None if undo_available else missing_target_error
        return (changes, undo_available, undo_error)

    return _finalize_answer_undo_entries(
        col,
        undo_target,
        changed_count,
        changes,
        force_merge=True,
    )


def _finalize_answer_undo_entries_with_fallback(
    col,
    primary_undo_target: Optional[int],
    fallback_undo_target: Optional[int],
    answered: int,
    changes: Any,
    force_merge: bool,
) -> Tuple[Any, bool, Optional[str]]:
    changes, undo_available, undo_error = _finalize_answer_undo_entries(
        col,
        primary_undo_target,
        answered,
        changes,
        force_merge=force_merge,
    )
    if undo_available:
        return (changes, undo_available, undo_error)

    if (
        fallback_undo_target is None
        or fallback_undo_target == primary_undo_target
        or answered <= 0
    ):
        return (changes, undo_available, undo_error)

    fallback_changes, fallback_available, fallback_error = _finalize_answer_undo_entries(
        col,
        fallback_undo_target,
        answered,
        changes,
        force_merge=False,
    )
    if fallback_available:
        return (fallback_changes, True, None)

    return (fallback_changes, False, undo_error or fallback_error)


def _add_custom_undo_entry(col, name: str) -> Optional[int]:
    add_custom_undo_entry = getattr(col, "add_custom_undo_entry", None)
    if not callable(add_custom_undo_entry):
        return None

    try:
        undo_target = int(add_custom_undo_entry(name))
    except Exception:
        return None

    return undo_target if undo_target > 0 else None


def _cleanup_unanswered_custom_undo_entry(
    col,
    undo_target: Optional[int],
    changes: Any,
) -> Any:
    if col is None or undo_target is None:
        return changes

    merge_undo_entries = getattr(col, "merge_undo_entries", None)
    if callable(merge_undo_entries):
        try:
            changes = _merge_op_changes(changes, merge_undo_entries(undo_target))
        except Exception:
            pass

    if _last_undo_step(col) != undo_target:
        return changes

    undo = getattr(col, "undo", None)
    if not callable(undo):
        return changes

    try:
        return _merge_op_changes(changes, _changes_from_result(undo()))
    except Exception:
        return changes


def _last_undo_step(col) -> Optional[int]:
    undo_status = getattr(col, "undo_status", None)
    if not callable(undo_status):
        return None

    try:
        step = int(getattr(undo_status(), "last_step", 0))
    except Exception:
        return None

    return step if step > 0 else None


def _merge_op_changes(left: Any, right: Any) -> Any:
    right = _changes_from_result(right)
    if right is None:
        return left

    if left is None:
        left = _empty_op_changes()
        if left is None:
            return right

    try:
        left.MergeFrom(right)
        return left
    except Exception:
        return right or left


def _changes_from_result(result: Any) -> Any:
    return getattr(result, "changes", result)


def _empty_op_changes() -> Any:
    try:
        from anki.collection import OpChanges

        return OpChanges()
    except Exception:
        return None


def _progress_update_for_mode(
    label: str,
    value: int,
    total: int,
    background: bool,
) -> None:
    if background:
        _queue_background_progress_update(label, value, total)
    else:
        _progress_update(value, total, label)


def _queue_background_progress_update(label: str, value: int, total: int) -> None:
    taskman = getattr(mw, "taskman", None) if mw is not None else None
    run_on_main = getattr(taskman, "run_on_main", None)
    if not callable(run_on_main):
        return

    run_on_main(lambda: _progress_update(value, total, label))


def _progress_cancel_requested() -> bool:
    progress = getattr(mw, "progress", None) if mw is not None else None
    want_cancel = getattr(progress, "want_cancel", None)
    if not callable(want_cancel):
        return False

    try:
        return bool(want_cancel())
    except Exception:
        return False


def _due_cards_query(col, deck_id: Optional[int]) -> Optional[str]:
    if deck_id is None:
        return "is:due -is:buried"

    deck = _get_deck(col, deck_id)
    if not isinstance(deck, dict):
        return None

    deck_name = str(deck.get("name") or "")
    if not deck_name:
        return None

    return f"deck:{_quote_search_value(deck_name)} is:due -is:buried"


def _excluded_cards_label(deck_id: Optional[int]) -> str:
    if deck_id is None:
        return "new and buried cards"
    return (
        "new cards, buried cards, cards currently in other decks, and cards "
        "Anki is not showing now"
    )


def _included_cards_label(deck_id: Optional[int]) -> str:
    if deck_id is None:
        return "due review and learning cards"
    return "queued due review and learning cards Anki would show for this deck"


def _quote_search_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _scope_label(col, deck_id: Optional[int]) -> str:
    if deck_id is None:
        return "the collection"

    deck = _get_deck(col, deck_id)
    if isinstance(deck, dict):
        return str(deck.get("name") or deck_id)
    return str(deck_id)


def _refresh_main_window() -> None:
    if mw is None:
        return

    try:
        mw.reset()
    except Exception:
        pass

    # `mw.reset()` emits Anki's legacy reset hooks, but the deck browser may
    # keep its existing HTML when Anki is already on the Decks screen.  The
    # Today-only limits are persisted correctly in that case, while the blue
    # new-card counts remain visibly stale until the user leaves and returns
    # to the screen.  Refresh the deck browser explicitly so triage actions
    # show their result immediately.
    deck_browser = getattr(mw, "deckBrowser", None)
    refresh = getattr(deck_browser, "refresh", None)
    if callable(refresh):
        try:
            refresh()
        except Exception:
            pass


def _progress_start(label: str, total: int) -> None:
    progress = getattr(mw, "progress", None) if mw is not None else None
    if progress is None:
        return

    try:
        progress.start(label=label, max=total, immediate=True)
    except TypeError:
        try:
            progress.start(label, total)
        except Exception:
            pass
    except Exception:
        pass


def _progress_update(
    value: int,
    total: Optional[int] = None,
    label: Optional[str] = None,
) -> None:
    progress = getattr(mw, "progress", None) if mw is not None else None
    if progress is not None:
        try:
            kwargs: Dict[str, Any] = {"value": value}
            if total is not None:
                kwargs["max"] = total
            if label is not None:
                kwargs["label"] = f"{label} {value} / {total}" if total else label
            progress.update(**kwargs)
        except TypeError:
            try:
                progress.update(value)
            except Exception:
                pass
        except Exception:
            pass

    app = getattr(mw, "app", None) if mw is not None else None
    process_events = getattr(app, "processEvents", None)
    if callable(process_events):
        try:
            process_events()
        except Exception:
            pass


def _progress_finish() -> None:
    progress = getattr(mw, "progress", None) if mw is not None else None
    if progress is None:
        return

    try:
        progress.finish()
    except Exception:
        pass


def _collect_target_decks(col) -> List[Tuple[int, str]]:
    collected: List[Tuple[int, str]] = []
    seen_ids = set()
    for deck_id, name in _all_deck_ids_and_names(col):
        if deck_id in seen_ids:
            continue

        deck = _get_deck(col, deck_id)
        if not isinstance(deck, dict) or bool(deck.get("dyn")):
            continue

        seen_ids.add(deck_id)
        collected.append((deck_id, name))

    collected.sort(key=lambda item: item[1].lower())
    return collected


def _deck_name_and_id(entry: object) -> Tuple[Optional[str], Optional[int]]:
    name = None
    deck_id = None

    if isinstance(entry, dict):
        name = entry.get("name")
        deck_id = entry.get("id")
    elif hasattr(entry, "name") and hasattr(entry, "id"):
        name = getattr(entry, "name", None)
        deck_id = getattr(entry, "id", None)
    elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
        first, second = entry[0], entry[1]
        if isinstance(first, str):
            name = first
            deck_id = second
        else:
            deck_id = first
            name = second

    if name is None or deck_id is None:
        return (None, None)

    try:
        return (str(name), int(deck_id))
    except Exception:
        return (None, None)


def _normalize_deck_id(deck_id: Optional[int]) -> Optional[int]:
    if deck_id is None:
        return None
    try:
        return int(deck_id)
    except Exception:
        return None


def _set_today_new_limit(col, deck_id: int, limit: int) -> bool:
    limit = int(limit)

    for obj in (getattr(col, "decks", None), getattr(col, "sched", None)):
        if obj is None or not hasattr(obj, "set_today_limit"):
            continue
        try:
            obj.set_today_limit(deck_id, "new", limit)
            if _deck_limit_matches(col, deck_id, limit):
                return True
        except TypeError:
            try:
                obj.set_today_limit(deck_id, limit)
                if _deck_limit_matches(col, deck_id, limit):
                    return True
            except Exception:
                pass
        except Exception:
            pass

    if _set_today_new_limit_on_deck(col, deck_id, limit):
        return True

    return False


def _set_today_new_limit_on_deck(col, deck_id: int, limit: int) -> bool:
    deck = _get_deck(col, deck_id)
    if not isinstance(deck, dict):
        return False

    base_new_limit = _base_new_limit(col, deck_id)
    updated = False
    if "newLimitToday" in deck:
        current_value = deck.get("newLimitToday")
        if isinstance(current_value, (dict, type(None))):
            today = _scheduler_today(col)
            if today is not None:
                deck["newLimitToday"] = {"limit": limit, "today": today}
                updated = True
        else:
            # Older Anki releases represented this as a scalar.
            deck["newLimitToday"] = limit
            updated = True
    if not updated and "extendNew" in deck:
        if base_new_limit is None:
            deck["extendNew"] = limit
        else:
            deck["extendNew"] = limit - int(base_new_limit)
        updated = True
    if not updated and "newLimit" in deck:
        deck["newLimit"] = limit
        updated = True

    if not updated:
        return False

    deck["mod"] = int(time.time())
    try:
        deck["usn"] = col.usn()
    except Exception:
        pass

    if _persist_deck(col, deck):
        return _deck_limit_matches(col, deck_id, limit)
    return False


def _scheduler_today(col) -> Optional[int]:
    sched = getattr(col, "sched", None)
    try:
        return int(getattr(sched, "today"))
    except (TypeError, ValueError):
        return None


def _persist_deck(col, deck: Dict[str, Any]) -> bool:
    decks = getattr(col, "decks", None)
    if decks is None:
        return False

    # update_dict() records a normal, undoable user operation.  The older
    # update() API is intended for syncing/merging and clears Anki's undo
    # stack, which makes collection-wide changes impossible to group.
    if hasattr(decks, "update_dict"):
        try:
            decks.update_dict(deck)
            return True
        except Exception:
            pass
    if hasattr(decks, "update"):
        try:
            decks.update(deck)
            return True
        except Exception:
            pass
    if hasattr(decks, "save"):
        try:
            decks.save(deck)
            return True
        except Exception:
            pass
    return False


def _get_deck(col, deck_id: int) -> Optional[Dict[str, Any]]:
    try:
        deck = col.decks.get(deck_id)
    except Exception:
        deck = None
    return deck if isinstance(deck, dict) else None


def _is_regular_deck(col, deck_id: int) -> bool:
    deck = _get_deck(col, deck_id)
    return isinstance(deck, dict) and not bool(deck.get("dyn"))


def _deck_limit_matches(col, deck_id: int, limit: int) -> bool:
    limits = _get_backend_deck_limits(col, deck_id)
    if limits is not None:
        try:
            if bool(getattr(limits, "new_today_active", False)) and int(
                getattr(limits, "new_today")
            ) == limit:
                return True
        except Exception:
            pass

    deck = _get_deck(col, deck_id)
    if not deck:
        return False
    new_limit_today = deck.get("newLimitToday")
    if new_limit_today == limit:
        return True
    if isinstance(new_limit_today, dict):
        stored_limit = new_limit_today.get("limit")
        stored_today = new_limit_today.get("today")
        try:
            if (
                stored_limit is not None
                and stored_today is not None
                and int(stored_limit) == limit
                and int(stored_today) == _scheduler_today(col)
            ):
                return True
        except (TypeError, ValueError):
            pass

    base_new_limit = _base_new_limit(col, deck_id)
    extend_new = deck.get("extendNew")
    if base_new_limit is not None and isinstance(extend_new, int):
        return int(base_new_limit) + int(extend_new) == limit

    if deck.get("newLimit") == limit:
        return True
    return False


def _get_backend_deck_limits(col, deck_id: int) -> Any:
    decks = getattr(col, "decks", None)
    if decks is None or not hasattr(decks, "get_deck_configs_for_update"):
        return None
    try:
        state = decks.get_deck_configs_for_update(deck_id)
        current_deck = getattr(state, "current_deck", None)
        if current_deck is None:
            return None
        return getattr(current_deck, "limits", None)
    except Exception:
        return None


def _base_new_limit(col, deck_id: int) -> Optional[int]:
    conf = _deck_config_dict(col, deck_id)
    if not isinstance(conf, dict):
        return None
    new_conf = conf.get("new")
    if not isinstance(new_conf, dict):
        return None
    try:
        return int(new_conf.get("perDay", 0))
    except Exception:
        return None


def _deck_config_dict(col, deck_id: int) -> Optional[Dict[str, Any]]:
    decks = getattr(col, "decks", None)
    if decks is None:
        return None

    config_for_deck = getattr(decks, "config_dict_for_deck_id", None)
    if callable(config_for_deck):
        try:
            conf = config_for_deck(deck_id)
            if isinstance(conf, dict):
                return conf
        except Exception:
            pass

    conf_for_deck = getattr(decks, "confForDid", None)
    if callable(conf_for_deck):
        try:
            conf = conf_for_deck(deck_id)
            if isinstance(conf, dict):
                return conf
        except Exception:
            pass

    return None


def _new_count_today(col, deck_id: int) -> int:
    sched = getattr(col, "sched", None)
    if sched is not None and hasattr(sched, "counts_for_deck_today"):
        try:
            counts = sched.counts_for_deck_today(deck_id)
            if hasattr(counts, "new"):
                return int(getattr(counts, "new") or 0)
        except Exception:
            pass

    deck = _get_deck(col, deck_id)
    if isinstance(deck, dict):
        new_today = deck.get("newToday")
        if isinstance(new_today, (list, tuple)) and len(new_today) >= 2:
            try:
                return int(new_today[1] or 0)
            except Exception:
                pass
    return 0


if gui_hooks is not None:
    gui_hooks.main_window_did_init.append(_setup_menu)
    if hasattr(gui_hooks, "deck_browser_will_show_options_menu"):
        gui_hooks.deck_browser_will_show_options_menu.append(_add_deck_options_menu_item)
    if hasattr(gui_hooks, "webview_will_set_content"):
        gui_hooks.webview_will_set_content.append(_inject_deck_context_menu_js)
    if hasattr(gui_hooks, "webview_did_receive_js_message"):
        gui_hooks.webview_did_receive_js_message.append(_handle_deck_context_menu_message)
