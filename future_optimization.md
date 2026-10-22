# Future library navigation optimizations

> **V00Ji and V00Ks withdrawn:** opening Artists rebooted the user's V00Ji player. Do not flash
> either build. The temporary
> sort-title arena violated stock record ownership; per-row name preparation is now disabled.
> Use known-good V002i (`Downloads/update_fast.tar`, SHA-256
> `4ec2ed5848fa1962a2cdf2ff37f3ca833bedd4e71ad3fa887a5559f61aabe079`) for rollback.
> Prior emulator/packaging passes below are historical, not proof of hardware correctness.

These are investigation and implementation candidates. The follow-up work below passed validation
as V007i, but did not produce a significant additional speedup on the user's device.
Prioritize small, independently tested changes over a general rewrite.
Operation counts below illustrate scaling; they are not measured Q2 navigation times.

## Current work: artist navigation

The current patch adds artist/album indexes, makes simple Album Artist LIKE lookups index-friendly,
and limits artist album metadata queries before grouping. It preserves album identity, same-name
artwork disambiguation, compilation-wide metadata, music filtering and the unscoped full-library
Coverflow path.

The first patch passed SQL tests on a synthetic 40,000-track library, firmware compilation,
native Coverflow tests, MIPS/playback tests and packaging for both variants. The user confirmed
faster artist-album navigation on V002i. V007i passed 1,645 navigation MIPS scenarios and 350
playback checks; Legacy V008s passed 1,259 navigation scenarios and 350 playback checks. Native
Coverflow and supporting/packaging checks also passed. These are not device latency measurements.

## Device measurements and next changes (V00Ai)

The diagnostic build passed 1,645 navigation scenarios, 350 playback checks and native logger
safety tests. Its SD-card log established:

- Artists took 0.64–1.45 s. All opens rejected the 1,330-row cache at the 256 KiB estimate,
  repeating 81,756 sort-key calls. The reported 262,337 bytes is the first budget crossing,
  **not the full estimate**. Next: measure the complete estimate and try a 512 KiB cap.
- Albums took 1.86–1.93 s with two substantial query/grouping passes; Genres took 1.31–1.39 s.
  Next: cache completed Albums/Genres lists under a shared 2 MiB limit, with explicit invalidation
  and eviction. Keep Artists separate and avoid caching track lists or widgets.
- Investigate preparing stock-compatible sort keys once per row, instead of repeatedly within
  comparisons. Preserve article trimming, ASCII/pinyin selection, Unicode behaviour and ties;
  the current log combines SQL and stock sorting and does not isolate conversion cost.
- Investigate reusing rich album groups to avoid the initial name-only grouping. A synthetic
  40,000-track SQL experiment preserved tested album identities with one rich result and reduced
  VM work about 32%. It did not validate stock pinyin/tie ordering, Unknown placeholders,
  representative rows, C execution or device speed. Keep those as implementation gates.
- All albums collection took 31 ms for 32 albums in two batches, with no fallback; opening playback
  then took 789 ms. Queue/page startup, not further batching, is the next playback investigation.
- Linux reported 117,884 KiB total and roughly 75–86 MiB available: consistent with a 128 MB
  device. Retain explicit bounds rather than treating all reported available RAM as a cache budget.

The next changes should each have a separate commit: Artists budget, completed-category cache,
sort-key reuse, and overlapping Albums grouping. Timings nest and must not be added together.

**Artists budget implemented:** raised to 512 KiB with the existing 4,096-row guard. Diagnostics
now record the complete estimate (`artists.cache_bytes`), even for rejected lists. Added tests for
a result between 256 and 512 KiB and for rejection above 512 KiB. Device fit remains to be measured.

**Category caching implemented:** completed Albums/Genres rows share 2 MiB and an 8,192-row guard.
Hits replay the stock title and deque effects; generation/settings changes invalidate entries.
Added MIPS checks for hits, copy independence, invalidation, scanning, shared-budget eviction,
oversized/empty/failed queries and allocation failure. The iPod diagnostic build V00Ci passed
1,646 navigation MIPS scenarios and 350 playback checks; native Coverflow and logger safety tests
also passed. Legacy V00Ds also passed 1,260 navigation scenarios and 350 playback checks. Device speed remains
unmeasured.

### Cold-sort compatibility gate

Disassembly of the two stock name comparators (`0x5b9d40`, `0x5ba658`) shows more than a
trim/pinyin/strcmp pipeline. They prefer directories to songs, use the title with a filename
fallback, extract numeric runs for natural ordering, classify several Unicode/encoding ranges,
and invoke language-specific helpers. A replacement comparator using plain prepared strings
would not preserve this ordering. Before enabling per-row keys, compare pairwise results and
whole-list order against the real stock comparators (both modes), including equal keys, numeric
runs, empty/article-only titles, CJK, Korean and accented names. Do not mistake mocked pinyin
or an ASCII-only microbenchmark for proof of stock compatibility.

**Sort preparation implementation:** retain both stock comparators and libcstl sorting. Prepare
only their trimmed/article-free title copies once per row, temporarily, under a 512 KiB/8,192-row
guard. Source-row-aware trim wrappers skip only arena-backed titles; all language/numeric logic
and filename fallback remain stock's. Restore original title pointers after records move. This
is intentionally narrower than precomputing pinyin or replacing the comparison algorithm. Add
separate preparation/comparison timers and verify whole-list order against allocation-fallback
sorting with the actual MIPS comparators before enabling a device test build.
The implementation passed 1,647 iPod navigation scenarios in V00Fi, including byte-for-byte title
pointer restoration after record movement, the 15-word libcstl sort ABI, allocation fallback,
whole-list ordering in both stock comparator modes and one normalization per prepared row.

**Albums overlap implementation:** one rich grouping supplies stock name materialization/sorting
and the existing split/identity pass for tagged names with unambiguous spelling. A cheap indexed
Unknown probe preserves the old untagged path. Case variants retain the original stock name query
but reuse complete rich metadata, so they do not add a third grouping pass. The synchronous
prefetch has an 8,192-row/2 MiB per-result guard and generation check; it is freed after the load.
Unfamiliar SQL, errors, scanning and size failures retain normal navigation. Full Coverflow and
artist-scoped queries are unchanged. The added count-distinct spelling guard reduces the earlier
theoretical benefit: measured clean 40k SQL VM work is now **1,577,400 -> 1,257,300 (~20%)** on both
SQLite 3.50.4 and 3.54.0, not hardware time. Tests compare rich representative rows and run the
actual stock getAllAlbum/row callback, staging and C split through SQLite on MIPS, including case
variants, NULL/empty albums, compilations, disc folders, quotes/wildcards and spoken exclusion.
The Unknown preflight explicitly uses `INDEXED BY q2pod_album_nocase`: SQLite 3.54 otherwise
selected a full scan in this fixture. Missing indexes skip the shortcut. The pinned probe uses
under 1,000 VM operations in the 40k regression rather than erasing the grouping savings.

### Final cross-variant validation

All four follow-up changes are committed independently on `perf/library-navigation`.

- iPod diagnostic **V00Ji**: 1,648 navigation MIPS scenarios and 350 playback checks passed;
  payload 352,056 bytes, update SHA-256
  `20af89fef0e8889c348d0d02e095f12e0accefd3bb7d08c157717c19d0a7374f`.
- Legacy **V00Ks**: 1,262 navigation MIPS scenarios and 350 playback checks passed;
  payload 298,120 bytes, update SHA-256
  `4f25dadc4cccb1bbc4756d4257f64e4933bc62f7d818e65a0de6fdf5ce572504`.
- SQL checks passed on SQLite 3.50.4 and 3.54.0; focused MIPS/SQLite prefetch checks passed for
  both variants, including Unknowns, case variants, missing-index fallback and deque cleanup.
- Native Coverflow and logger safety tests passed. Both variants passed metadata/cover dispatch,
  ReplayGain, LDAC, headset I/O, Bluetooth DROP and final packaging/asset checks.

These results validate tested behaviour and packaging, not device latency or peak memory.
The next device session must verify the full Artists estimate/cache hit, category cache activity,
remaining stock-comparison time, Albums prefetch/fallback decisions and playback continuity.
Pinyin/language-specific comparison work remains stock's; Unknown Albums retain their old path.

### V00Ji Artists reboot and ownership correction

The user reported a reboot when opening Artists. The SD log contained fresh V00Ji boot headers
with no completed navigation records after them; it does not identify an exact crash PC. Boot
RAM snapshots showed ample available memory, but do not establish peak usage at the fault.

Inspection of stock libcstl's `_deque_iterator_set_value` and the firmware's `stSongInfo` copy
callback (`0x5b3b1c`) exposed an unsafe operation: iterator assignment can free destination
strings and allocate copies. V00Ji replaced titles with interior pointers into one arena and
assumed raw record movement. Those pointers cannot be freed individually, and copied titles
would also lack the arena header used for restoration. The previous mock used raw byte moves
and missed this boundary. This is a concrete ownership defect consistent with the device crash;
the log alone cannot prove it was the only cause.

Correction: remove all title substitution/arena state and comparator bypasses. Retain only a
15-word ABI-preserving timing wrapper around unchanged stock sorting. Keep the bounded Artists
and category caches and Albums grouping reuse. The replacement regression invokes the **real
MIPS stock copy callback** with a strict allocator, to reject interior and duplicate frees.
Per-row name/pinyin precomputation is deferred until it can avoid mutating owning records.

### Replacement approach: non-owning reference sorting and playback profiling

Implemented a different sorting strategy without touching song/title pointers: sort integer
references with the same libcstl algorithm and original comparator, then apply the permutation
through stock's owning-copy callback and one temporary owning row. Owning swaps are O(n); no
second full owning library is built. Metadata has a conservative 1 MiB estimate and 65,000-row
guard (~569 KiB estimate for 43,086 tracks), with small-list/range/scan/allocation fallbacks.
There is no persistent order cache and no new SQL schema/order change. Trimming, natural/language
comparison and tie decisions remain stock's; this does not precompute pinyin or normalized keys.

Real shipped MIPS libcstl/QEMU differential tests passed sizes 0–65,001, both synthetic comparator
modes, identical-key ties, metadata, exact ID order and comparison counts, owning-string cleanup,
initial array/header allocation failures, scans and subranges. In the synthetic 43,086-row cases:

- owning copies: 730,682 -> 129,226 and 907,979 -> 129,217;
- emulated CPU: ~1.68 s -> 1.06 s and ~2.04 s -> 0.92 s.

These are **QEMU results with synthetic comparators**, not Q2 timings or a promised speedup. The
firmware still calls its actual original name comparators. The MIPS suite separately checks that
adapter and the real stock owning-copy callback. Physical-player timing is still required.

Playback changes are diagnostic only: time stock page initialization, `player_start`, Q2 Pod's
pre-start work, stock `mclStartPlayer`, the first stock UI/cover refresh, ratings binding, iPod
binding/theme/sync, total page initialization and the next idle boundary. This should distinguish
stock/player work from Q2 Pod additions and from surrounding navigator/UI work. It does not
measure first audible PCM; no audio callback performs SD writes. Stage timings remain nested.

Validation: iPod V00Oi passed 1,650 MIPS navigation scenarios and Legacy V00Ps passed 1,264;
both passed 350 advanced playback/wheel checks and supporting M4B, ID3, LDAC, headset and
Bluetooth checks. Native Coverflow, bounded diagnostics, SQL correctness/plans and both-variant
packaging checks passed. The navigation harness must execute the real `playing_refresh` after
its new private binding, rather than automatically mocking it; correcting that test boundary
restored the existing artwork rollover tests without changing firmware. Q2 hardware results
for this replacement sorter and playback breakdown follow below.

### V00Oi device results and diagnostic cleanup

The physical player completed both All Songs opens with 43,086 tracks. Reference sorting took
5,784–5,802 ms versus V00Li's 7,080–7,098 ms (about 18% faster), retaining exactly 2,021,648
sort-key calls per open. Comparison consumed 5,184–5,201 ms and applying the permutation took
546–551 ms. Total class loading was 7,501 ms initially and 8,519 ms on repeat, followed by
492/315 ms to the next idle boundary. The metadata estimate was 582,568 bytes (~569 KiB).

Playback-page opening took 645–686 ms. Stock `mclStartPlayer` consumed 355–362 ms, with another
~270–318 ms inside stock `player_start`; initial stock refresh took 1–17 ms. Q2 Pod preparation,
ratings and iPod binding stages were 0–2 ms combined. These are synchronous timings, not first
audible output. Further playback optimization is deferred; no new playback behaviour was added.

After these measurements, remove the temporary SD logger, timing hooks/counters, diagnostic-only
tests and build option. Keep the performance/ownership regression tests and optimization history.
Normal firmware no longer creates or appends `q2-navigation-diagnostics.log`; an existing card
log is left untouched and can be archived or removed on the computer.

Rebased onto `origin/main` at `7efbff5` (1.4.2 plus the latest MQA fix), preserving upstream's
hashed list lookups, scoped Coverflow replacement, decoder folder-speed update, larger scratch
layout and games/apps. Final diagnostic-free builds:

- iPod **V00Ri**: 1,739 MIPS navigation scenarios and 352 playback/wheel checks passed;
  payload 395,128 bytes; update SHA-256
  `36a91f7ab6505759f90c8e17c9636341e1cdb49be3fa1e7b915f8ae0b3915393`.
- Legacy **V00Rs**: 1,310 MIPS navigation scenarios and 351 playback/wheel checks passed;
  payload 327,992 bytes; update SHA-256
  `11a20ab550fb0badecb88a0a0c04e25e11f545ab74c37fc5967d9f865ac1e1a8`.
- Both variants passed supporting metadata, ReplayGain, LDAC, headset/Bluetooth and packaging
  checks. Native Coverflow/SQL and the real-libcstl reference-sort regression passed. Binary
  checks confirmed no logger path/symbols, unchanged stock `player_start` entry and initial
  refresh call, and matching build-input hashes. Multi-day hardware testing is pending.

### October 28 refresh: upstream 1.5.4

Rebased the performance branch onto `origin/main` at `a817b50`, retaining the library
optimizations without restoring navigation diagnostics. Preserved upstream's playlist sorting,
video exclusion, oversized-track admission guard, MP3 gapless/FLAC paths, decoder futex waits,
power-saving defaults and UI changes. Experimental MCU idle sleep remains off by default.

- iPod **V00Si**: 2,003 MIPS navigation scenarios and 353 playback/wheel checks passed;
  payload 465,976 bytes; update SHA-256
  `cdebe286cca580620e261599a9f8a125d24fa0748e53a24d1f5b7a336ff002a3`.
- Legacy **V00Ts**: 1,485 MIPS navigation scenarios and 352 playback/wheel checks passed;
  payload 377,960 bytes; update SHA-256
  `b7a7051f22ff547cc5bc607755b509a69c32fe26c97e6370fba8ca3455af0b9c`.
- Both variants passed metadata, ReplayGain, LDAC, headset/Bluetooth, decoder-wait, installed
  MP3 gapless hooks and packaging checks. Native Coverflow/SQL and real-libcstl reference-sort
  regression passed. Build-input hashes match; no navigation logger path/symbols remain, and
  the stock player entry and initial refresh call remain unchanged. Hardware testing is pending;
  this refresh does not establish a fix for the reported missing Ayreon albums.

### October 31 refresh: upstream 1.6.0 development

Rebased onto `origin/main` at `8909332`, keeping upstream's single-edition build after Legacy
removal. Retained Night Shift Auto, card-app metadata/sleep timers, library folder exclusions,
the Shuffle Songs sort bypass and Bluetooth updates. Scope expansion now precedes our bounded
Unknown probes and artist-query cache; expanded query storage is freed on every result path.
Navigation diagnostics remain removed.

iPod **V00Ui** passed 2,152 MIPS execution scenarios and 358 playback/wheel checks, plus native
Coverflow, library SQL/marker scope, real-libcstl reference-sort, metadata, ReplayGain, LDAC,
headset/Bluetooth, decoder waits, MP3 gapless and packaging checks. The upstream Night Shift tests
still expected On -> Off after Auto was added; test-only corrections cover Off -> On -> Auto ->
Off, Auto temperature changes and clock-driven tint removal. Focused and full reruns passed;
firmware was not changed to satisfy the old expectations.

Payload: 504,856 bytes; update SHA-256
`eab6cc87c43890e540ae8f79f1efd7f1894a2ad6b925ed28dff10d72981d6454`.
Build-input hashes match, no navigation logger path/symbols remain, and the stock player entry
and first refresh call remain unchanged. Hardware testing is pending.

### November 7 refresh: upstream `3c727d4`

Rebased onto the current upstream integration, still versioned 1.6.7. Kept upstream's direct
`staged_into` collection and Songs-to-showlist loading, sorted shared-folder pass, deterministic
first-disc/track artwork, theme engine, oversized Ogg/Opus handling and audio fixes. Our rich
Albums prefetch now uses upstream's `ALBUM_TRACK` expression. Our indexes, bounded caches,
Unknown probes, album batches and reference sorter remain; experimental module flags retain
upstream's new off-by-default settings. The detailed summary is in
`docs/upstream-rebase-2026-11-07.md`.

**V00Vi** passed 2,839 MIPS navigation scenarios, 758 playback/wheel checks and 3,639 host firmware
tests. Native Coverflow, library SQL/marker scope and real-libcstl reference-sort tests passed.
Supporting metadata, ReplayGain, LDAC, headset/Bluetooth, decoder waits, real MP3 decode-chain
and packaging checks passed. The extended real-player suites (`hci_ao`, `bt_resample`,
`xfade_player`, `hci_natural`, `player_seam`) also passed with generated audio.

Test-only integration corrections add the new disc/track fixture columns, pass the scoped
artist argument in a new Coverflow test and check our existing 4 KiB query buffer boundary in
the new host suite. Firmware did not need rebuilding for those test corrections.

Payload: 686,248 bytes; update SHA-256
`5ea90ba453e94b51b720006c328e0dd48a78ab5593da761d8c031da1f83f87d0`.
Build-input hashes match. Our temporary navigation logger/timing hooks remain absent; upstream's
new `player_start` hook and its own crash/cold-open reporting remain. Physical-player timings
and multi-day stability remain unmeasured for this build.

The strict regression reproduced the invalid/interior free in **both original V00Ji and V00Ks**
artifacts using the real MIPS copy callback, while validating their historical source and binary
hashes. Corrected iPod **V00Li** passes the same focused ownership test in both comparator modes.
The test's mocked lowercase table was also enlarged to its actual 384-entry size, eliminating a
test-only allocation overrun exposed by the new deep-copy checks.

Corrected-build validation completed:

- **V00Li** (iPod diagnostics): 1,648 navigation scenarios and 350 playback checks passed;
  payload 351,080 bytes; update SHA-256
  `cca4410bd1f1a2a5b029790ef905f3406c66ffae790ff236caace885d04d8864`.
- **V00Ms** (Legacy): 1,262 navigation scenarios and 350 playback checks passed;
  payload 297,096 bytes; update SHA-256
  `5047184d7b711711c62d3073d72286c87d1747dfe02cf771c0fbdfd0800c7e62`.
- Both corrected variants passed the focused real-copy ownership regression, supporting metadata,
  ReplayGain, LDAC, headset/Bluetooth checks and final packaging/asset checks.

The user subsequently tested V00Li successfully on the physical player and reported noticeably
snappier navigation; this session showed no further reboot. The three other library improvements
remain enabled; per-row sort-key preparation is disabled, not claimed as delivered.

### V00Li device results: working caches and the All Songs bottleneck

The supplied session contains 1,330 artist rows, 4,465 completed album rows, 1,960 completed genre
rows and **43,086 songs**. Class timings below are loader timings, not complete tap-to-visible
latency; nested query and sorting durations must not be added together.

| Action | First class load | Repeated class load | Interpretation |
| --- | --- | --- | --- |
| Artists | 1,443 ms | 12–23 ms | Query cache hits take 2–4 ms; no repeated name sort. |
| Albums | 2,771 ms | 27 ms | Completed-category cache works; cold grouping shortcut fell back. |
| Genres | 1,340 ms | 6 ms | Completed-category cache works. Cold sort alone took 835 ms. |
| All Songs | 8,768 ms | 9,228 ms | Not cached; stock sorting repeats across all 43,086 rows. |

- Full Artists estimate: **309,653 bytes (~302.4 KiB)**, comfortably within the 512 KiB cap but
  above the old 256 KiB cap. The first Artists sort took 186 ms out of a 1,433 ms query/cache-fill
  interval, so sorting was not the dominant cold Artists cost in this sample.
- Albums logged `albums.prefetch_fallback` detail 0, rows -1. That label combines expected Unknown
  handling with probe/index/query/generation failure; it does **not** establish which occurred.
  The category-cache gain is confirmed, but the one-rich-grouping speedup is not demonstrated
  on this library. Add distinct fallback reasons before choosing a cold Albums change.
- All Songs sorting took **7,080 and 7,098 ms**, about 77–81% of class load time. Each open added
  exactly **2,021,648 sort-key calls**. The following class-to-idle intervals were 476 and 314 ms,
  yielding roughly 9.24–9.54 seconds from loader entry to that idle boundary. Safe, non-mutating
  sorting/preparation work is the next measured target, not another generic SQL index or an
  unbounded cache of 43k owning song records. Retain real-copy ownership regression coverage.
- All albums collection remained fast: 31–32 ms, two batches, 428 final tracks, no fallback.
  Opening the playing page took 471–756 ms; the measured stock queue loader took only 2–4 ms.
  Remaining playback-start delay lies outside the batched collection and measured loader work.
- First-time artwork workers took 744–2,212 ms for 1–6 jobs. Reopening cached covers avoided this
  worker work; the 8-album repeat view built widgets in 1 ms.
- Sampled MemAvailable stayed around 76–85 MiB before All Songs and fell to about 35–48 MiB after
  its two loads. Low MemFree alone does not imply exhaustion. These system snapshots do not
  measure process heap peaks or establish a leak; watch repeated All Songs loads if investigating
  its memory footprint. Do not infer a memory guarantee from this session.

## 1. Replace Unknown-row expansion with an existence check

**Follow-up implemented and validated:** category probes keep the stock song callback
but add `LIMIT 1` and bypass name sorting. This avoids full song expansion without duplicating
stock tag predicates. Coverflow's separate Unknown check remains a candidate.

- **Where:** `patch/navigation.c`: `ringnav_localclass`, `class_query`;
  `patch/coverflow.c`: `drop_unknown`.
- **Confirmed cost:** category loads query all matching songs merely to decide whether their
  trailing Unknown row should remain, then discard those records. This affects Albums, Artists,
  Genres and Composers; main Coverflow performs a similar Unknown Album check.
- **Proposal:** use `SELECT 1 ... LIMIT 1` with the same tag conditions and music-only scope,
  without constructing or sorting full song records.
- **Preserve:** NULL versus empty tag behaviour, Album Artist fallback, spoken-audio filtering,
  staging-deque state, row counts and empty-category behaviour. Do not turn a failed query into a
  confirmed absence of matching songs.
- **Priority:** high; bounded change with potential benefit across several categories.

## 2. Index rating lookups in memory

- **Where:** `patch/navigation.c`: `rate_all`, `rated_open`, `rate_slot`, `rate_kept`;
  `patch/coverflow.c`: `coverflow_rated` and rating-based sorting.
- **Confirmed cost:** rating lists load the library and compare each song against the combined
  favourite/rating entries. With 40,000 songs and 2,000 entries, the nested search can approach
  80 million comparisons. Individual album-rating lookups also linearly search up to 4,096 slots.
- **Proposal:** build a sorted lookup or hash table once per rating/favourite generation, and reuse
  it while filtering or sorting. Avoid changing the on-disk rating format.
- **Preserve:** favourites take precedence as five hearts, song/CUE keys, album IDs, stable ordering
  within equal ratings, duplicate-key behaviour, and invalidation after rating/favourite edits.
- **Priority:** high for large rated collections.

## 3. Index play counts in memory

- **Where:** `patch/navigation.c`: `mp_rank`, `most_played`, `album_plays`.
- **Confirmed cost:** each song can search all 512 play-count slots. A 40,000-track cold load can
  therefore perform roughly 20 million slot comparisons. Coverflow's Most Played sort uses the
  same pattern while summing album plays.
- **Proposal:** build a key-to-count/rank lookup once, then scan songs with direct lookups.
- **Preserve:** recency tie-breaking, top-100 selection, CUE keys, album play totals and the existing
  warm Most Played cache. Invalidate when counts change or old entries are evicted.
- **Priority:** high for cold Most Played loads and album play-count sorting.

## 4. Avoid repeated library searches for missing favourite titles

- **Where:** `patch/navigation.c`: `fav_titles`.
- **Confirmed cost:** the library is loaded once when needed, but each favourite with a missing
  title searches that entire in-memory library by path and CUE start. This is not a separate
  database query per favourite, but still scales as missing titles times library size.
- **Proposal:** index the staged library by path and CUE start, or use suitably indexed targeted
  database lookups if they are cheaper overall.
- **Preserve:** CUE segment identity, original ordering, existing nonempty titles, and filename
  fallback when no tagged library match exists.
- **Priority:** medium; benefits collections with many old/untitled favourite records.

## 5. Reuse grouped metadata for full-library Coverflow

- **Where:** `patch/coverflow.c`: `load`, `split`, `music_albums`, `rank_by`, `sorted`.
- **Confirmed cost:** a cold load performs overlapping stock album grouping, split grouping and
  music-only grouping. Year/recently-added ordering can add another grouped query. Warm opens
  already reuse album lists until `library_gen` changes, so this is not a full rebuild on every open.
- **Proposal:** investigate sharing a grouped album metadata result, including sort fields, or a
  generation-scoped cache. Retain the existing identity rules rather than replacing grouping with
  album name alone.
- **Preserve:** album artist/folder identity, disc-folder merging, stock name order, Unknown Album,
  artwork representatives, album ratings, sort direction, stable ties and scan/delete invalidation.
- **Priority:** medium; greater regression risk than replacing an isolated lookup.

## 6. Calculate shared artwork folders once

- **Where:** `patch/coverflow.c`: `folder_shared` and artwork job preparation in `load`.
- **Confirmed cost:** every uncached album artwork job can scan all albums to decide whether its
  folder is shared. Preparing many jobs can therefore scale quadratically, before the worker starts.
- **Proposal:** build a folder-to-distinct-album lookup/count once while preparing jobs.
- **Preserve:** directory boundaries, distinct album identity and the rule that a shared folder's
  cover image must not be incorrectly assigned to another album.
- **Priority:** medium; mainly cold artwork builds or cache refreshes.

## 7. Virtualize large Coverflow lists

- **Where:** `patch/coverflow.c`: `covers`, `changed`.
- **Confirmed cost:** the carousel creates a widget for every album, even though only nearby art
  needs to be visible. The flat rendering fallback also walks all children on selection changes.
- **Proposal:** recycle a bounded window of widgets around the selected album.
- **Preserve:** logical selection, wheel acceleration, letter jumps, animations, utility cards,
  artist-view bounds and restoring position after tracks/Back.
- **Priority:** investigate only after query improvements; larger UI change requiring device checks.

## 8. Batch the artist All albums playback expansion

**Follow-up implemented and validated:** up to 16 album names per batch, with a 512-song
limit (513th row signals fallback). Failed/oversized batches retain individual queries. Complete
album identity and disc/track/CUE ordering remain unchanged; no selected-artist-only filtering.

- **Where:** `patch/coverflow.c`: `play_all`, `coverflow_album_tracks`.
- **Confirmed cost:** the All albums card runs a separate song query for each displayed album.
  The new album index can help individual queries, but does not eliminate repeated query setup,
  record copying and sorting.
- **Proposal:** fetch the required tracks in a bounded batch, group them by the existing album
  identity, and concatenate them in the displayed album order.
- **Preserve:** complete compilation albums (not only tracks credited to the selected artist),
  disc/track/CUE order, no duplicates, queue class and unavailable-storage behaviour.
- **Priority:** medium for artists with large discographies; this is a playback action, not page load.

## 9. Verify genre/composer and year query opportunities

- **Where:** stock category loaders, reached through `ringnav_localclass`/`class_query`, and
  Coverflow's `year_sql`/`rank_by`.
- **Known:** the current patch adds no dedicated genre/composer/year indexes. Genre and composer
  detail navigation uses the stock category-specific queries. The scanner's genre column is named
  `style`; do not assume the schema uses the UI label `genre`.
- **Not established:** which indexes stock already creates, the exact plans on its bundled SQLite,
  and whether these paths have a comparable redundant-query problem. Inspect the extracted stock
  firmware/schema before declaring these lookups unindexed.
- **Proposal:** capture exact SQL and inspect `EXPLAIN QUERY PLAN`; test collation-compatible
  category/album indexes only where useful. Preserve LIKE wildcard and Unknown-tag behaviour.
- **Year distinction:** globally sorting albums by `MAX(year)` requires album aggregation; a plain
  year index is not automatically sufficient. Shared album metadata may be the better improvement.
- **Priority:** next SQL investigation, not a confirmed missing-index fix.

## 10. Long Songs and playlist picker: lower-priority investigation

- **Long Songs:** `long_songs`, `ls_show` load and examine the library on each open. Missing file
  durations require TagLib probes, but those already run on a worker and use a persistent duration
  cache with binary-search lookups. Consider caching the filtered result per library/duration
  generation before changing this comparatively well-cached path.
- **Playlist Add Songs:** `ple_filter` searches title/artist/album across its retained picker records.
  It does not reload the database for every search. Profile filtering and result-widget creation
  before adding database indexes; arbitrary substring search is not generally accelerated by an
  ordinary name index.

## Validation for each future change

### Low-RAM constraints

The measured device appears to have 128 MB RAM; retain 32 MiB as a conservative compatibility case
for unmeasured hardware, and do not assume all RAM is available to the UI. The follow-up Artists
sorted-query cache now has a conservative 512 KiB
storage budget and a 4,096-row guard, with one entry only. Over-budget, failed and empty loads are
not retained; generation, SQL, callback and sorting-key changes invalidate it. It does not cache
widgets or whole-library song lists. Broader LRU caching remains deferred. Actual low-memory
playback, scans and cold/warm navigation still need device testing.

### Checklist

1. Keep it separate from the current artist patch and from other optimization candidates.
2. Add behaviour regressions for empty libraries, NULL/empty tags, quotes/wildcards, CUE tracks,
   duplicate album names, compilations, multi-disc folders and spoken-audio exclusions as applicable.
3. Use synthetic 40,000-track libraries. Compare result identities/order as well as operation counts;
   indexes can change SQLite's arbitrary representative row within a group.
4. Run the SQL checks, native Coverflow tests and built MIPS/navigation tests for both UI variants.
5. Check read-only/locked databases, memory allocation failures, rescans/deletes and cache invalidation.
6. Verify firmware size/packaging and updater identity before producing a flashable test build.
7. Measure cold/warm navigation and playback continuity on a Q2 when available. SQL VM counts and
   mocked emulator instruction counts are not substitutes for hardware timing.
