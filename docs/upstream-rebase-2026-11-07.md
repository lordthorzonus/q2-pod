# November 7 upstream rebase

Rebased `perf/library-navigation` from the October 31 upstream snapshot (`8909332`) onto
`origin/main` at `3c727d4`. Upstream still labels this snapshot 1.6.7, with newer merged fixes.

## Performance changes relevant to our library

| Upstream change | Benefit | Integration |
| --- | --- | --- |
| `staged_into` / zero-copy query collection (`025cfcd`) | Queries write directly into their destination deque instead of deep-copying whole-library results. Reduces allocation work and peak RAM. | Kept upstream's ownership model, not our older staging-copy implementation. |
| Songs loads directly into its displayed deque (`cea52bb`) | Avoids holding the library twice while opening Songs. | Kept `songs_load` alongside our reference sorter. |
| Sorted-pass shared-folder detection (`ac34f21`) | Replaces the albums-squared folder check during cold Cover Flow preparation. | Kept the sorted pass and upstream cold-open trace. |
| Oversized Ogg/Opus metadata handling (`dcef912` and follow-ups) | Streams large comments without decoding embedded pictures into multiple large allocations; guards stock cover extraction too. | Kept the new `xiph.c` reader and guards. |

These are code-level improvements, not newly measured Q2 timings. Lower memory pressure may
also help responsiveness and stability, but no device speedup is promised by this rebase.

## Conflicts with our work

- **Query ownership:** older commits in our history restored/copied the staging deque. Those
  hunks were resolved in favour of upstream's direct-destination collection.
- **Songs loading:** our category-cache wrapper and upstream's direct Songs loader touched the
  same function. Both are retained: Songs uses the new loader; Artists/Albums/Genres retain our
  bounded caching behaviour.
- **Album artwork:** upstream now chooses the lowest disc, track, then path instead of an
  arbitrary grouped track (`89fe0dc`). Our rich Albums prefetch uses the same `ALBUM_TRACK`
  expression, preserving that new artwork rule.
- **Cover Flow:** retained upstream's new motion/layout, sorted folder checks and cold-open
  handling while preserving our scoped artist metadata queries and bounded All albums batches.
- **Build/test refactors:** retained the generated theme headers and shared `UI_SOURCES` list;
  our sort module joins that list. Test fixtures now supply upstream's disc/track columns, and
  the host query-boundary test checks our existing 4 KiB SQL buffer rather than upstream's 2 KiB.

Our ordinary SQLite indexes, bounded caches, Unknown probes, album batches and non-owning
reference sorting remain. Upstream has not replaced those optimizations.

## Other notable upstream changes

- Theme engine and geometry sets; new Classic pages, Modern theme, revised Cover Flow controls.
- Playback/gapless, format-transition, resume, queue-delete and per-output EQ fixes.
- Ratings backup on the card and chapters for spoken files in more formats.
- Watchdog/crash reporting and scan/art progress breadcrumbs.
- More free-memory headroom requested through the kernel's watermark setting; not a proven LDAC fix.
- Experimental audio-notifier/rotator/PWM module changes are off by default again. The new build
  keeps that default; `--dev` alone does not enable them. Low Power and Wheel QS were removed upstream.

Our temporary `q2-navigation-diagnostics.log` instrumentation remains removed. Upstream's own
crash logs and cold-open breadcrumbs remain intact; this is not a logging-free upstream build.
