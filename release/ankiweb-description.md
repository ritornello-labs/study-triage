Study Triage adds quick triage actions for days when you need to reduce today's Anki workload.

Use it when you want to keep reviews moving but avoid adding more new cards, or when you need to quickly answer a batch of due cards.

Actions:

- Set Today's New Cards to 0
- Answer Due Cards as Good
- Answer Due Cards as Easy

You can run actions collection-wide from Tools -> Study Triage. You can also run deck-specific actions from a deck's cog menu or by right-clicking a deck name on the Decks screen.

Notes:

- The new-card limit uses Anki's Today only limit, so it resets automatically on the next Anki day.
- Deck actions apply to the selected deck and its subdecks, matching Anki's deck search behavior.
- Filtered decks can use the Good/Easy actions; the new-card limit action is only available for regular decks.
- Actions show a count before running and group the change into a single Anki undo step.
- Good/Easy actions use Anki's native bulk grader on current releases, avoiding
  partial batches when search order differs from the live reviewer queue.

Requires Anki 2.1.55 or newer.

![Animated Study Triage deck-menu tour](https://ritornello.dev/media/ankiweb/2026-07-30/study-triage/preview.gif)

<img src="https://ritornello.dev/media/ankiweb/2026-07-30/study-triage/study-triage-workbench.png" alt="Study Triage deck menu screenshot">

![Study Triage's explicit deck-level actions](https://ritornello.dev/media/ankiweb/2026-07-30/study-triage/gallery-02.png)

[Watch the full Study Triage preview (MP4)](https://ritornello.dev/media/ankiweb/2026-07-30/study-triage/demo.mp4)

Source and issue tracker: [https://github.com/ritornello-labs/study-triage](https://github.com/ritornello-labs/study-triage)
