#include "navigation.h"
#include "library.h"

extern int stock_dbquery_trampoline(const char *, const char *, void *, int);
extern int stock_sorted_query_trampoline(const char *, const char *, void *, int);
extern int stock_content_query_trampoline(const char *, const char *, void *, void *, int);

/* One bounded, deep-copied Artists query, not a cache of UI widgets or track lists. Keeping the
 * cache below the stock loader preserves its title, staging/showlist copies and Unknown row. */
static struct {
    void *rows, *row, *arg;
    char *sql, *db;
    unsigned gen;
    int content, sort, count, name_mode;
} artist_cache __attribute__((section(".scratch")));
/* Include record/deque storage and conservative per-allocation overhead, not just row count.
 * Oversized lists keep stock behaviour rather than retaining memory needed by audio playback. */
static int artist_cache_fits(void *rows, const char *db, const char *sql) {
    unsigned bytes = (unsigned)(strlen(db) + strlen(sql)) + 256;
    for (unsigned i = 0; i < deque_size(rows); ++i) {
        void *r = deque_at(rows, i);
        bytes += 0x60 + 96;
        for (unsigned off = REC_NAME; off <= REC_ALBUM_ARTIST; off += 4) {
            const char *s = P(r, off);
            if (s) bytes += (unsigned)strlen(s) + 1;
        }
    }
    /* The caller's 4,096-row guard bounds this accounting for uncacheable results too. */
    return bytes <= 512 * 1024;
}
int artist_query_cached(int content, const char *db, const char *sql, void *row, void *arg,
                               int sort) {
    unsigned gen = library_gen;
    int name_mode = *(volatile unsigned char *)SORT_NAME_MODE;
    void *dir = P(tools_pdeq_directory, 0);
    if (artist_cache.rows && ((gen & 1) || gen != artist_cache.gen ||
        content != artist_cache.content || row != artist_cache.row || arg != artist_cache.arg ||
        sort != artist_cache.sort || name_mode != artist_cache.name_mode ||
        strcmp(db, artist_cache.db) || strcmp(sql, artist_cache.sql))) {
        deque_destroy(artist_cache.rows);
        free(artist_cache.sql), free(artist_cache.db);
        artist_cache.rows = 0;
    }
    if (artist_cache.rows) {
        deque_clear(dir);
        deque_assign(dir, artist_cache.rows);
        return artist_cache.count;
    }
    int n = content == 2 ? stock_sorted_query_trampoline(db, sql, row, (int)arg)
          : content ? stock_content_query_trampoline(db, sql, row, arg, sort)
                    : stock_dbquery_trampoline(db, sql, row, (int)arg);
    if (n > 0 && n <= 4096 && (unsigned)n == deque_size(dir) && !(gen & 1) && gen == library_gen &&
        artist_cache_fits(dir, db, sql)) {
        char *s = strdup(sql), *d = strdup(db);
        if (s && d) {
            void *copy = _create_deque("stSongInfo");
            if (copy) {
                deque_init_copy(copy, dir);
                artist_cache.rows = copy, artist_cache.sql = s, artist_cache.db = d;
                artist_cache.gen = gen, artist_cache.content = content;
                artist_cache.row = row, artist_cache.arg = arg, artist_cache.sort = sort;
                artist_cache.count = n;
                artist_cache.name_mode = name_mode;
                return n;
            }
        }
        free(s), free(d);
    }
    return n;
}

/* Completed category rows only: never retain widgets or a song queue. Both entries share one
 * budget; touching an entry makes it newest. The stock loader's only non-query effect for these
 * two classes is music_nagvation_title; replay it on a hit and leave staging empty as stock does. */
#define CATEGORY_CACHE_BYTES (2 * 1024 * 1024)
static struct {
    void *rows;
    unsigned gen, bytes, used;
    int cls, mode, artist;
} category_cache[2] __attribute__((section(".scratch")));
static unsigned category_clock __attribute__((section(".scratch")));
static void category_drop(unsigned i) {
    if (category_cache[i].rows) deque_destroy(category_cache[i].rows);
    category_cache[i].rows = 0;
    category_cache[i].bytes = 0;
}
int category_get(int cls) {
    unsigned gen = library_gen;
    int mode = *(volatile unsigned char *)SORT_NAME_MODE, artist = I(artist_type, 0);
    for (unsigned i = 0; i < 2; ++i) {
        if (category_cache[i].rows && ((gen & 1) || category_cache[i].gen != gen ||
            category_cache[i].mode != mode || category_cache[i].artist != artist)) category_drop(i);
        if (!category_cache[i].rows || category_cache[i].cls != cls) continue;
        void *list = P(p_deque_showlist, 0);
        music_nagvation_title(cls);
        deque_clear(list);
        deque_assign(list, category_cache[i].rows);
        deque_clear(P(tools_pdeq_directory, 0));
        category_cache[i].used = ++category_clock;
        return (int)deque_size(list);
    }
    return -1;
}
void category_keep(int cls, unsigned gen, int n) {
    if ((cls != CLASS_ALBUMS && cls != 0xf006) || n <= 0 || n > 8192 ||
        (gen & 1) || gen != library_gen) return;
    void *list = P(p_deque_showlist, 0);
    if ((unsigned)n != deque_size(list)) return;
    unsigned bytes = 256;
    for (unsigned i = 0; i < (unsigned)n; ++i) {
        void *r = deque_at(list, i);
        bytes += 0x60 + 96;
        for (unsigned off = REC_NAME; off <= REC_ALBUM_ARTIST; off += 4) {
            const char *s = P(r, off);
            if (s) bytes += (unsigned)strlen(s) + 1;
        }
        if (bytes > CATEGORY_CACHE_BYTES) return;
    }
    unsigned slot = !category_cache[0].rows ? 0 : !category_cache[1].rows ? 1 :
                    category_cache[0].used <= category_cache[1].used ? 0 : 1;
    category_drop(slot);
    unsigned other = 1 - slot;
    if (bytes + category_cache[other].bytes > CATEGORY_CACHE_BYTES) category_drop(other);
    void *copy = _create_deque("stSongInfo");
    if (!copy) return;
    deque_init_copy(copy, list);
    category_cache[slot].rows = copy, category_cache[slot].gen = gen;
    category_cache[slot].bytes = bytes, category_cache[slot].used = ++category_clock;
    category_cache[slot].cls = cls;
    category_cache[slot].mode = *(volatile unsigned char *)SORT_NAME_MODE;
    category_cache[slot].artist = I(artist_type, 0);
}
