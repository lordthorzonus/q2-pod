# November 13 upstream integration

Target: `origin/main` at `f242dac5` (1.8.2 development), previously `3c727d49` (1.6.7).
The default upstream branch is `main`, not `master`.

## Speed and memory improvements upstream

- **Unknown rows stop after the first matching song** (`d720fdcc`, released in 1.7.4).
  This overlaps our bounded Unknown probes. The integration shares upstream's probe flag,
  assembles its single LIMIT after scope expansion, keeps our no-sort dispatch and preserves the row on query failure instead of caching an
  incomplete result. It must not append LIMIT twice.
- **Album/detail and Recently Added queries are bounded**, with indexes and more targeted
  reads for deletes/scan work (`43ddd949` and related changes, 1.7.4). These complement our
  artist-membership indexes, scoped rich metadata reads and bounded All albums batches.
- **List reloads no longer leak deque storage** (`f919dc78`, 1.7.4): upstream reported about
  8 MB per Songs reopen on a 65,000-song library, and smaller losses in other categories.
  This is separate from our caches and reference sorter; the upstream fix is retained.
- **Cover Flow rendering and Fast Navigation:** upstream reports roughly 50 rather than 32
  frames/s, asynchronous loading during letter navigation and small cached covers. The mode
  is optional and leaves a disk-space reserve. These are upstream figures, not measurements
  of this combined firmware on our player. The 1.8.1 name Fast Navigation replaces Large
  Library Mode; its saved setting is retained.
- Queue-copy reductions and background playlist-art reads reduce work/memory in other paths.

## Changes required in our work

- Stock is now **Shanling V1.36**, not V1.32. The original ZIP was downloaded from Shanling's
  forum-linked Drive file and verified against upstream's SHA-256:
  `4e298cab6c12d86cfc55565645f7e3ae11d3fb44677a93ca13991e7184ecec4e`.
- Mapped our three query-sort call sites, both stock comparators, owning record-copy routine
  and comparator-selector byte from V1.32 to V1.36 using upstream's stock alignment tool.
  Emulator fixtures also need the new imports/GOT slots; old addresses must not ship.
- Kept upstream's modular source structure. Our bounded category caches are now in
  `patch/library_cache.c`, not a restored copy of the old navigation state/playlist code.
  The existing query and artist-page hooks remain in navigation.c because their callers and
  scope state still live there; they are integration edits, not new navigation features.
- Kept our artist scope through album splitting, year ordering and the delayed Cover Flow
  open, while retaining upstream's new veil, playlist covers, Unknown resume and ownership.
- Kept upstream's shared build source lists and the new modules rather than restoring the
  older single-file compilation recipe. Updated changed test signatures and SQL fixtures.
- The backup branch `backup/library-navigation-before-2026-11-13-rebase` preserves the
  complete previous history. The rebased optimization commit consolidates that history's
  net changes, so withdrawn title substitution and temporary diagnostics are not replayed.

Our ordinary SQLite artist indexes, scoped metadata reads, bounded category caches, album
prefetch/batches and stock-comparator reference sorting remain. The sorter still falls back
to stock beyond its own 65,000-reference budget; this is **not** a library scan limit.

## Other notable upstream changes

- V1.36 removes the old scan/song limit; Q2 Pod no longer imposes its former 65,000 limit.
  MQA decoding/its ineffective setting are removed; such files play as ordinary FLAC.
- Library album view and Songs ordering persist across restarts. Queue view can show 500
  upcoming shuffled songs. Cover Flow opens on the queued song's album when it can.
- AirPlay output via a separately installed app, playlist cover art/Cover Flow, battery
  history, Smart Wi-Fi, duration scanning and expanded card-app integrations.
- Security fixes for Wi-Fi file transfer and shell-quoted file operations, bounded image/EPUB
  handling and Last.fm session keys instead of requiring an account password on the card.
- Numerous standby, resume/headphones-required, audiobook, volume, wheel and UI fixes.

Temporary navigation/playback timing instrumentation remains removed. Legitimate upstream
crash reporting and artwork diagnostics remain. Experimental kernel options stay off by default.

## Validation status

Integration is not yet approved for installation. The SQL/index regression, native Cover Flow,
8,588 host firmware tests (3 expected failures) and 1,436 Python tool unit tests passed.
The host record fixtures needed length modelling for 64-bit reads overlapping stock's 32-bit
string fields; production cache accounting was not weakened to work around those fixtures.
The initial V00Xi build also passed 740 playback/wheel checks, shipped-libcstl reference-sort
differentials and supporting metadata/Bluetooth/MP3 decode-chain checks. A final rebuild and
full MIPS/audio validation are pending. The final candidate is **V00Yi**, 782,680 payload bytes,
SHA-256 `8835ab8e898de79ccbf7add02f1fe74962deeace1982fc4d855bf003548242fc`.
Its build-input hash and archive checksum match; its shipped-libcstl sort differential passed.
For 43,086 rows the differential made 129,226/129,217 owning copies versus stock's
730,682/907,979 in the two comparator modes, with identical order, ties and metadata.
These are emulator regressions, not current physical-device timings.
No new artifact has been copied to Downloads.
V00Vi remains the validated rollback.

The V1.32-to-V1.36 address sweep reports no remaining executable/test addresses on the old
layout, but flags one pre-existing upstream prose reference in `docs/internals.md`: `0x4c43e4`
in the Bluetooth page description. That same reference exists at `origin/main`; it is not a
patch site introduced by this branch.
