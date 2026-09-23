from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace


def _load_addon_module() -> ModuleType:
    addon_path = Path(__file__).resolve().parents[1] / "__init__.py"
    spec = importlib.util.spec_from_file_location("study_triage_under_test", addon_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load Study Triage add-on module")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeckContextMenuTest(unittest.TestCase):
    def test_refresh_main_window_rerenders_deck_browser(self) -> None:
        addon = _load_addon_module()
        calls: list[str] = []
        addon.mw = SimpleNamespace(
            reset=lambda: calls.append("reset"),
            deckBrowser=SimpleNamespace(refresh=lambda: calls.append("refresh")),
        )

        addon._refresh_main_window()

        self.assertEqual(calls, ["reset", "refresh"])

    def test_deck_context_menu_js_sends_deck_specific_message(self) -> None:
        addon = _load_addon_module()

        script = addon._deck_context_menu_js()

        self.assertIn("contextmenu", script)
        self.assertIn("td.decktd", script)
        self.assertIn("open:(\\d+)", script)
        self.assertIn(addon.DECK_CONTEXT_MESSAGE_PREFIX, script)

    def test_parse_deck_context_menu_message(self) -> None:
        addon = _load_addon_module()

        self.assertEqual(
            addon._parse_deck_context_menu_message("study-triage-deck-context:123"),
            123,
        )
        self.assertIsNone(
            addon._parse_deck_context_menu_message("study-triage-deck-context:not-a-deck")
        )
        self.assertIsNone(addon._parse_deck_context_menu_message("open:123"))

    def test_js_message_result_matches_hook_shape(self) -> None:
        addon = _load_addon_module()

        self.assertEqual(addon._handled_js_message_result((False, None)), (True, None))
        self.assertTrue(addon._handled_js_message_result(False))


if __name__ == "__main__":
    unittest.main()
