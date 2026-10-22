/* Artist album candidates include other artists' albums of the same name: artwork keys and
 * album-wide year metadata must agree with the main Albums list. Keep LIKE's stock semantics.
 * UNION lets ordinary column indexes serve the album-artist fallback on older SQLite versions. */
#define ARTIST_ALBUM_SCOPE \
    "album COLLATE NOCASE in (select album from songtable where songer like %s) or album is null"
#define ALBUM_ARTIST_ALBUM_SCOPE \
    "album COLLATE NOCASE in (select album from songtable where albumsonger<>'' and albumsonger like %s union " \
    "select album from songtable where (albumsonger is null or albumsonger='') and songer like %s) or album is null"
#define ALBUM_ARTIST_MATCH \
    "((albumsonger<>'' and albumsonger like %.*s) or ((albumsonger is null or albumsonger='') and songer like %.*s))"

/* No expression/partial indexes, schema-version changes, or dependency on a recent SQLite. */
#define LIBRARY_INDEX_SQL \
    "create index if not exists q2pod_album_nocase on songtable(album COLLATE NOCASE);" \
    "create index if not exists q2pod_artist_album on songtable(songer COLLATE NOCASE,album COLLATE NOCASE);" \
    "create index if not exists q2pod_albumartist_album on songtable(albumsonger COLLATE NOCASE,album COLLATE NOCASE);"

static inline int library_quote(char *sql, unsigned cap, unsigned *n, const char *s) {
    if (*n + 3 >= cap) return 0;
    sql[(*n)++] = '\'';
    for (; s && *s; ++s) {
        if (*n + 3 >= cap) return 0;
        if (*s == '\'') sql[(*n)++] = '\'';
        sql[(*n)++] = *s;
    }
    sql[(*n)++] = '\'';
    sql[*n] = 0;
    return 1;
}
