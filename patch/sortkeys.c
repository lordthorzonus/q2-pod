#ifdef SORT_TEST
#include "sortkeys_test.h"
#else
#include "offsets.inc"
#include "peq.h"
#include "stock.h"
#endif

/* libcstl passes each deque iterator as seven words, by value, followed by the comparator. */
typedef struct { unsigned word[7]; } name_iterator;
#define ITER_ARGS(it) (it).word[0], (it).word[1], (it).word[2], (it).word[3], \
                      (it).word[4], (it).word[5], (it).word[6]
#ifndef SORT_COMPARE_A
#define SORT_COMPARE_A ((void *)0x5cc870) /* V1.36 library_name_cmp_pinyin */
#define SORT_COMPARE_B ((void *)0x5cd188) /* V1.36 library_name_cmp */
#endif
#define REFERENCE_LIMIT 65000u
#define REFERENCE_BYTES (1024 * 1024u) /* conservative estimate, including deque bookkeeping */
typedef union { void *row; unsigned original; } sort_slot;
static struct {
    sort_slot *slots;
    void (*compare)(const void *, const void *, int *);
    volatile int busy;
} refs __attribute__((section(".scratch")));
extern volatile unsigned library_gen;

static void reference_less(const void *a, const void *b, int *less) {
    refs.compare(refs.slots[*(const unsigned *)a].row, refs.slots[*(const unsigned *)b].row, less);
}

/* The owning records stay untouched while stock libcstl sorts a deque of integer references.
 * Apply that permutation with O(n) swaps through stock's REAL owning copy callback and a
 * one-record owning temporary. No borrowed string is ever stored in an owning record. */
static int reference_sort(void *dir, unsigned n, name_iterator first, name_iterator last,
                          void *compare) {
    unsigned gen = library_gen;
    int done = 0;
    void *indices = 0, *temporary = 0;
    sort_slot *slots = 0;
    unsigned bytes = n * (sizeof(sort_slot) + 2 * sizeof(unsigned)) + 65536;
    name_iterator begin, end;
    deque_begin(&begin, dir);
    deque_end(&end, dir);
    if (memcmp(&first, &begin, sizeof begin) || memcmp(&last, &end, sizeof end)) goto out;
    if ((gen & 1) || n > REFERENCE_LIMIT || bytes > REFERENCE_BYTES) goto out;
    slots = calloc(n, sizeof(sort_slot) + sizeof(unsigned));
    if (!slots) goto out;
    unsigned *where = (unsigned *)(slots + n);
    indices = _create_deque("int");
    if (!indices) goto out;
    deque_init(indices);
    temporary = _create_deque("stSongInfo");
    if (!temporary) goto out;
    deque_init(temporary);
    for (unsigned i = 0; i < n; ++i) {
        slots[i].row = deque_at(dir, i);
        _deque_push_back(indices, (int)i);
    }
    refs.slots = slots;
    refs.compare = compare;
    deque_begin(&begin, indices);
    deque_end(&end, indices);
    algo_sort_if(ITER_ARGS(begin), ITER_ARGS(end), reference_less);
    if (gen != library_gen || n != deque_size(dir)) goto out;
    /* Validate before touching any owning row; where is still the calloc'd visitation array. */
    for (unsigned i = 0; i < n; ++i) {
        unsigned k = *(unsigned *)deque_at(indices, i);
        if (k >= n || where[k]++) goto out;
    }
    for (unsigned i = 0; i < n; ++i) slots[i].original = where[i] = i;
    _deque_push_back(temporary, deque_at(dir, 0));
    void *scratch = deque_at(temporary, 0);
    for (unsigned i = 0; i < n; ++i) {
        unsigned wanted = *(unsigned *)deque_at(indices, i), j = where[wanted];
        if (j == i) continue;
        void *a = deque_at(dir, i), *b = deque_at(dir, j);
        int copied;
        song_record_copy(scratch, a, &copied);
        song_record_copy(a, b, &copied);
        song_record_copy(b, scratch, &copied);
        unsigned moved = slots[i].original;
        slots[i].original = wanted, slots[j].original = moved;
        where[wanted] = i, where[moved] = j;
    }
    done = 1;
out:
    refs.slots = 0;
    refs.compare = 0;
    if (temporary) deque_destroy(temporary);
    if (indices) deque_destroy(indices);
    free(slots);
    return done;
}

void ringnav_name_sort(name_iterator first, name_iterator last, void *compare) {
    void *dir = P(tools_pdeq_directory, 0);
    unsigned n = deque_size(dir);
    if (n >= 64 && (compare == SORT_COMPARE_A || compare == SORT_COMPARE_B) &&
        !__sync_lock_test_and_set(&refs.busy, 1)) {
        int sorted = reference_sort(dir, n, first, last, compare);
        __sync_lock_release(&refs.busy);
        if (sorted) return;
    }
    algo_sort_if(ITER_ARGS(first), ITER_ARGS(last), compare);
}
