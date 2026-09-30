# Changelog

## 0.3.14 - 2026-09-30

- Refresh deck-browser counts immediately after a triage action.
- Show the real populated-tree workflow and link optional support through ritornello.dev/support.

## 0.3.13 - 2026-07-23

- Fix Good/Easy batches leaving a few due cards behind with
  `not at top of queue`.
- Use Anki's native bulk grader on current releases so arbitrary search results
  are graded atomically instead of being sent through the ordered reviewer API.
- Preserve the older per-card compatibility path and add native-rating and
  fallback regression coverage.

## 0.3.12 - 2026-07-23

- Fix collection-wide new-card limit changes losing their custom undo target.
- Persist deck limit changes through Anki's undo-aware deck update API so the
  batch remains a single Study Triage undo action.
- Add regression coverage for incremental undo merging across large collections.

## 0.3.11 - 2026-07-16

- Fix Today-only new-card updates on current Anki releases.
- Preserve both active and expired Today-only review limits while triaging new cards.
- Add regression coverage for the deck-limit update and a disposable Anki GUI interaction.
