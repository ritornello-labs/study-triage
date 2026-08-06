Study Triage adds quick triage actions for days when you need to reduce today's Anki workload.

## See it in Anki

![New cards spread across a crowded deck tree](https://ritornello.dev/media/ankiweb/2026-08-06-v4/study-triage/gallery-01.png)

![The same deck tree muted after setting today's new cards to zero](https://ritornello.dev/media/ankiweb/2026-08-06-v4/study-triage/gallery-02.png)

[2-second full-resolution MP4](https://ritornello.dev/media/ankiweb/2026-08-06-v4/study-triage/demo.mp4)

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

Source and issue tracker: [https://github.com/ritornello-labs/study-triage](https://github.com/ritornello-labs/study-triage)
