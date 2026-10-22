#!/usr/bin/env python3
"""SQLite-only artist navigation regressions; no firmware, compiler or device required.

Uses the firmware's SQL macros. Query assembly mirrors scoped_rank_query; C execution and the
navigation integration are covered separately by test/coverflow.py and test/patch.py.
"""
import ast
import pathlib
import re
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = '\n'.join((ROOT / 'patch' / p).read_text(encoding='utf-8') for p in
                   ('library.h', 'library_scope.h', 'offsets.inc', 'coverflow.c')).replace('\\\n', '')


def macro(name):
    value = re.search(r'^#define ' + name + r' (.*)$', SOURCE, re.M)[1]
    return ''.join(ast.literal_eval(t) if t.startswith('"') else macro(t)
                   for t in re.findall(r'"(?:[^"\\]|\\.)*"|\b[A-Z][A-Z_0-9]*\b', value))


def quote(s):
    return "'" + s.replace("'", "''") + "'"


def scope(artist, aa):
    q = quote(artist)
    return macro('ALBUM_ARTIST_ALBUM_SCOPE') % (q, q) if aa else macro('ARTIST_ALBUM_SCOPE') % q


def scoped(sql, predicate):
    head, tail = sql.split(' from songtable', 1)
    where = tail.startswith(' where ')
    return head + ' from songtable where (' + predicate + ')' + (' and ' if where else '') + tail[7 if where else 0:]


def operations(db, sql):
    ticks = 0
    def progress():
        nonlocal ticks
        ticks += 1
        return 0
    db.set_progress_handler(progress, 100)
    try:
        rows = db.execute(sql).fetchall()
    finally:
        db.set_progress_handler(None, 0)
    return rows, ticks * 100


def main():
    db = sqlite3.connect(':memory:')
    db.execute('create table songtable(id integer primary key,album text,songer text,fileurl text,albumsonger text,year integer,cd_num integer default 0,track integer default 0)')
    db.executemany('insert into songtable(id,album,songer,fileurl,albumsonger,year) values(?,?,?,?,?,?)', (
        (i + 1, f'Album {i // 10}', f'Artist {i // 100}', f'/mnt/mmc/Music/{i // 10}/{i}.flac',
         '' if (i // 10) % 3 == 0 else f'Artist {i // 100}', 1980 + (i // 10) % 45)
        for i in range(40000)))
    extra = [
        ('Shared', 'The Cure', '/mnt/mmc/Music/Cure/1.flac', 'The Cure', 1989),
        ('shared', 'Other', '/mnt/mmc/Music/Other/1.flac', 'Other', 1999),
        ('Compilation', 'The Cure', '/mnt/mmc/Music/Various/1.flac', 'Various', 1990),
        ('Compilation', 'Guest', '/mnt/mmc/Music/Various/2.flac', 'Various', 2020),
        ('Fallback', 'The Cure', '/mnt/mmc/Music/Fallback/CD1/1.flac', '', 1987),
        ('Fallback', 'The Cure', '/mnt/mmc/Music/Fallback/Disc 2/2.flac', '', 1988),
        ('Null AA', 'The Cure', '/mnt/mmc/Music/Null/1.flac', None, 0),
        ('Shared', 'The Cure', '/mnt/mmc/Audiobooks/Book/1.mp3', 'The Cure', 2026),
        ('Podcast', 'The Cure', '/mnt/mmc/Podcasts/Show/1.mp3', 'The Cure', 2026),
        ('M4B', 'The Cure', '/mnt/mmc/Music/book.M4B', 'The Cure', 2026),
        ('', '', '/mnt/mmc/Music/Unknown/1.flac', '', 0),
        (None, None, '/mnt/mmc/Music/Unknown/2.flac', None, None),
    ]
    for artist in ("Artist's name", '100% Real', 'Under_score', 'Quote"Artist', 'Björk', '周杰伦', 'The Cure'):
        extra.extend([(artist, artist, f'/mnt/mmc/Music/quoted/{len(extra)}.flac', '', 2001),
                      (artist + ' tagged', 'Guest', f'/mnt/mmc/Music/tagged/{len(extra)}.flac', artist, 2002)])
    db.executemany('insert into songtable(id,album,songer,fileurl,albumsonger,year) values(?,?,?,?,?,?)',
                   ((40001 + i, *r) for i, r in enumerate(extra)))
    db.commit()
    old_rows = db.execute('select * from songtable').fetchall()
    # Index installation must not remove or merge full-library album identities. Representative
    # tracks in a SQL group are unspecified, so compare its keys rather than an arbitrary row ID.
    full_queries = [macro('ALBUM_SQL'), macro('MUSIC_ALBUM_SQL')]
    def album_keys(sql):
        return {(r[1].lower() if r[1] else r[1], (r[4] or '').lower(),
                 r[3].rsplit('/', 1)[0] if not r[4] else '') for r in db.execute(sql)}
    full_before = [album_keys(sql) for sql in full_queries]
    db.executescript(macro('LIBRARY_INDEX_SQL'))
    db.executescript(macro('LIBRARY_INDEX_SQL'))  # safe on subsequent boots
    assert db.execute('select * from songtable').fetchall() == old_rows
    assert len([r for r in db.execute('pragma index_list(songtable)') if r[1].startswith('q2pod_')]) == 3
    assert [album_keys(sql) for sql in full_queries] == full_before

    # The prefetch's extra aggregate must not change rich representatives on this fixture.
    # Ambiguous spellings and Unknowns are deliberately rejected by the C fast path.
    rich = db.execute(macro('ALBUM_SQL')).fetchall()
    prefetched = db.execute(macro('ALBUM_PREFETCH_SQL')).fetchall()
    assert [r[:5] for r in prefetched] == rich
    assert any(r[1] is None and r[5] == 0 for r in prefetched)
    probe = ("select 1 from songtable indexed by q2pod_album_nocase where (album is null or album COLLATE NOCASE='') and "
             + macro('MUSIC_WHERE') + ' limit 1')
    probe_rows, probe_ops = operations(db, probe)
    probe_plan = '\n'.join(r[3] for r in db.execute('explain query plan ' + probe))
    assert probe_rows == [(1,)] and probe_ops < 1000 and 'q2pod_album_nocase' in probe_plan, probe_plan
    clean = lambda sql: sql.replace(' from songtable', ' from songtable where id<=40000', 1)
    name_sql = 'select id,album,songer,fileurl from songtable group by album COLLATE NOCASE'
    _, name_ops = operations(db, clean(name_sql))
    _, rich_ops = operations(db, clean(macro('ALBUM_SQL')))
    _, prefetch_ops = operations(db, clean(macro('ALBUM_PREFETCH_SQL')))
    assert prefetch_ops < name_ops + rich_ops, (prefetch_ops, name_ops, rich_ops)

    # Indexable LIKE branches must retain the old fallback expression's results, including NULL,
    # quoted names, Unicode, stock wildcards, the empty artist and case-insensitive ASCII matches.
    artists = ('The Cure', 'the cure', '', "Artist's name", '100% Real', 'Under_score',
               'Quote"Artist', 'Björk', '周杰伦', '%', 'Artist 12', 'Missing')
    for artist in artists:
        q = quote(artist)
        old = "ifnull(nullif(albumsonger,''),songer) like " + q
        new = macro('ALBUM_ARTIST_MATCH').replace('%.*s', '%s') % (q, q)
        ids = lambda p: set(db.execute('select id from songtable where ' + p))
        assert ids(old) == ids(new), artist
        for aa in (0, 1):
            predicate = scope(artist, aa)
            member = old if aa else 'songer like ' + q
            # NULL names cannot be matched by IN; explicitly retain them for Unknown handling.
            names = {r[0].lower() for r in db.execute('select album from songtable where ' + member) if r[0] is not None}
            candidate_ids = {r[0] for r in db.execute('select id from songtable where ' + predicate)}
            candidate_paths = {r[3] for r in old_rows if r[0] in candidate_ids}
            expected = {r[0] for r in old_rows if r[1] is None or r[1].lower() in names}
            assert candidate_ids == expected, (artist, aa)
            for music in (False, True):
                base = macro('MUSIC_ALBUM_SQL' if music else 'ALBUM_SQL')
                # Compare group identity and album-wide max(year), not SQLite's arbitrary bare id.
                base = base.replace(' from songtable', ',max(year) from songtable', 1)
                full = db.execute(base + ' order by max(year),album COLLATE NOCASE').fetchall()
                small_sql = scoped(base, predicate) + ' order by max(year),album COLLATE NOCASE'
                small = db.execute(small_sql).fetchall()
                identity = lambda r: (r[1], (r[4] or '').lower(), r[3].rsplit('/', 1)[0] if not r[4] else '', r[5])
                wanted = [identity(r) for r in full if r[3] in candidate_paths]
                assert [identity(r) for r in small] == wanted, (artist, aa, music)
                assert len(small_sql.encode()) < 3072

    # A compilation's latest year includes the other artist's track, and another artist's Shared
    # album remains available for artwork disambiguation. Spoken-only albums stay filtered out.
    sql = scoped(macro('MUSIC_ALBUM_SQL').replace(' from songtable', ',max(year) from songtable', 1), scope('The Cure', False))
    rows = db.execute(sql).fetchall()
    assert next(r[-1] for r in rows if r[1] == 'Compilation') == 2020
    assert len([r for r in rows if r[1].lower() == 'shared']) == 2
    assert not {'Podcast', 'M4B'} & {r[1] for r in rows}

    # Require a substantial reduction in VM work, not machine-dependent ms. SQLite versions differ:
    # some scan the outer album index rather than seeking it, but still avoid full-library grouping.
    full = macro('ALBUM_SQL') + ' order by max(year),album COLLATE NOCASE'
    small = scoped(full, scope('Artist 12', True))
    _, old_ops = operations(db, full)
    _, new_ops = operations(db, small)
    plan = '\n'.join(r[3] for r in db.execute('explain query plan ' + small))
    for index in ('q2pod_album_nocase', 'q2pod_artist_album', 'q2pod_albumartist_album'):
        assert index in plan, plan
    assert new_ops < old_ops / 2, (old_ops, new_ops, plan)
    match = macro('ALBUM_ARTIST_MATCH').replace('%.*s', '%s') % (quote('Artist 12'), quote('Artist 12'))
    _, old_match_ops = operations(db, "select id from songtable where ifnull(nullif(albumsonger,''),songer) like 'Artist 12'")
    _, new_match_ops = operations(db, 'select id from songtable where ' + match)
    assert new_match_ops < old_match_ops / 10, (old_match_ops, new_match_ops)
    # Bound worst-case quoting, not just typical artist names (stock tags hold 255 bytes).
    longest = scope("'" * 255, True)
    assert len(longest) < 1536
    assert len(scoped(macro('MUSIC_ALBUM_SQL'), longest)) < 3072
    db.close()
    print(f'Artist SQL: correctness and indexed plans passed on SQLite {sqlite3.sqlite_version}; '
          f'40k-track metadata VM work {old_ops:,} -> {new_ops:,}, '
          f'artist lookup {old_match_ops:,} -> {new_match_ops:,} (not hardware timings).')
    print(f'Album prefetch: 40k clean-library grouping VM work {name_ops+rich_ops:,} -> '
          f'{prefetch_ops:,}; representative/Unknown checks passed (not hardware timings).')


if __name__ == '__main__':
    main()
