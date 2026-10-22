#!/usr/bin/env python3
"""Run the reference-sort implementation against the shipped MIPS libcstl under QEMU.

No mocked deque/sort implementation: compare exact ID order, owning-copy counts and cleanup.
Requires a built firmware directory, qemu-mipsel, clang/lld and unsquashfs (Linux).
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from build import FLAGS, ROOT

HEADER = r'''
extern void *test_directory;
#define tools_pdeq_directory (&test_directory)
#define P(p,o) (*(void **)((char *)(p)+(o)))
void compare_a(const void *, const void *, int *);
void compare_b(const void *, const void *, int *);
#define SORT_COMPARE_A ((void *)compare_a)
#define SORT_COMPARE_B ((void *)compare_b)
void *ref_calloc(unsigned, unsigned);
void ref_free(void *);
void *ref_create(const char *);
void ref_destroy(void *);
#define calloc ref_calloc
#define free ref_free
#define _create_deque ref_create
#define deque_destroy ref_destroy
int memcmp(const void *, const void *, unsigned);
unsigned deque_size(const void *);
void *deque_at(const void *, unsigned);
void deque_init(void *);
void _deque_push_back(void *, ...);
void deque_begin(void *, const void *);
void deque_end(void *, const void *);
void algo_sort_if(unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,
                  unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,void *);
void song_record_copy(void *, const void *, int *);
'''

HARNESS = r'''
#include "sortkeys_test.h"
#undef calloc
#undef free
#undef _create_deque
#undef deque_destroy
void *calloc(unsigned,unsigned);
void free(void *);
void *malloc(unsigned);
void *memcpy(void *, const void *, unsigned);
void *memset(void *, int, unsigned);
unsigned strlen(const char *);
int strcmp(const char *, const char *);
int snprintf(char *,unsigned,const char *,...);
int printf(const char *,...);
void exit(int);
long clock(void);
void *_create_deque(const char *);
void deque_destroy(void *);
int _type_register(unsigned,const char *,void *,void *,void *,void *);
typedef struct { unsigned w[7]; } iterator;
void iterator_next_n(void *,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,int);
void ringnav_name_sort(iterator,iterator,void *);
#define WORDS(i) (i).w[0],(i).w[1],(i).w[2],(i).w[3],(i).w[4],(i).w[5],(i).w[6]
typedef struct { unsigned id; char *strings[11]; unsigned values[10]; } record;
typedef char record_size_must_match_stock[(sizeof(record)==0x58)?1:-1];
void *test_directory;
volatile unsigned library_gen;
static unsigned live, copies, compares, aux, headers, fail_alloc, fail_header, creates;
static void check(int ok,const char *what) {
    if (!ok) { printf("FAIL: %s\n",what); exit(1); }
}
static char *own(const char *text) {
    unsigned n=strlen(text)+1,*p=malloc(n+8);
    check(p!=0,"string allocation");
    p[0]=0x51734f57; p[1]=n;
    memcpy(p+2,text,n); ++live;
    return (char *)(p+2);
}
static void release(char *text) {
    if (!text) return;
    unsigned *p=(unsigned *)text-2;
    check(p[0]==0x51734f57,"invalid/interior/double string free");
    p[0]=0; --live; free(p);
}
static void init(void *p,int *ok) { memset(p,0,sizeof(record)); *ok=1; }
static void destroy(void *p,int *ok) {
    record *r=p;
    for (unsigned i=0;i<11;++i) release(r->strings[i]);
    memset(p,0,sizeof(record)); *ok=1;
}
void song_record_copy(void *p,const void *q,int *ok) {
    if (p==q) { *ok=1; return; }
    destroy(p,ok);
    memcpy(p,q,sizeof(record));
    record *r=p; const record *s=q;
    for (unsigned i=0;i<11;++i) if (s->strings[i]) r->strings[i]=own(s->strings[i]);
    ++copies; *ok=1;
}
static int natural(const record *a,const record *b) {
    if (a->values[0]!=b->values[0]) return a->values[0]<b->values[0]?-1:1;
    return strcmp(a->strings[3],b->strings[3]);
}
void compare_a(const void *p,const void *q,int *ok) {
    ++compares; *ok=natural(p,q)<0;
}
void compare_b(const void *p,const void *q,int *ok) {
    ++compares; *ok=strcmp(((const record *)p)->strings[3],((const record *)q)->strings[3])<0;
}
void *ref_calloc(unsigned n,unsigned size) {
    if (fail_alloc) return 0;
    void *p=calloc(n,size); if (p) ++aux; return p;
}
void ref_free(void *p) { if (p) --aux; free(p); }
void *ref_create(const char *name) {
    if (++creates==fail_header) return 0;
    void *p=_create_deque(name); if (p) ++headers; return p;
}
void ref_destroy(void *p) { --headers; deque_destroy(p); }
static unsigned rng;
static unsigned random_word(void) { rng=rng*1664525+1013904223; return rng; }
static void *songs(unsigned n,int ties) {
    void *dq=_create_deque("stSongInfo"); deque_init(dq);
    const char *words[]={"The Cure","Disc 2","Disc 10","Björk","周杰伦","","The ","An Album","Éclair"};
    rng=123;
    for (unsigned i=0;i<n;++i) {
        record r; int ok; init(&r,&ok);
        r.id=i; unsigned key=random_word(); r.values[0]=ties?0:key%37;
        char path[128]; snprintf(path,sizeof path,"/mnt/mmc/Music/%u/Disc 2/track %u.flac",key%200,i);
        r.strings[1]=own(path); r.strings[2]=own(path);
        r.strings[3]=own(ties?"Identical":words[key%9]);
        r.strings[4]=own("Album"); r.strings[5]=own("Artist"); r.strings[8]=own("Album Artist");
        r.values[2]=i%2; r.values[3]=i%11; /* independent disc/CUE-like metadata must survive */
        _deque_push_back(dq,&r); destroy(&r,&ok);
    }
    return dq;
}
static void bounds(void *dq,unsigned n,int subset,iterator *a,iterator *b) {
    iterator begin; deque_begin(&begin,dq);
    if (!subset) { *a=begin; deque_end(b,dq); }
    else {
        iterator_next_n(a,WORDS(begin),5);
        iterator_next_n(b,WORDS(begin),(int)n-2);
    }
}
static void run(unsigned n,int mode,int ties,int failure,int subset) {
    check(!live && !aux && !headers,"clean start");
    void *original=songs(n,ties),*candidate=songs(n,ties);
    void *compare=mode?(void *)compare_b:(void *)compare_a;
    iterator a,b; bounds(original,n,subset,&a,&b);
    copies=compares=0; long at=clock();
    algo_sort_if(WORDS(a),WORDS(b),compare);
    long old_us=clock()-at; unsigned old_copies=copies, old_compares=compares;
    bounds(candidate,n,subset,&a,&b);
    test_directory=candidate; creates=0;
    fail_alloc=failure==1; fail_header=failure==2?1:failure==3?2:0;
    library_gen=failure==4?1:0;
    copies=compares=0; at=clock();
    ringnav_name_sort(a,b,compare);
    long new_us=clock()-at; unsigned new_copies=copies,new_compares=compares;
    fail_alloc=fail_header=library_gen=0;
    check(deque_size(candidate)==n,"row count");
    for (unsigned i=0;i<n;++i) {
        record *x=deque_at(original,i),*y=deque_at(candidate,i);
        check(x->id==y->id,"exact stock order including ties");
        check(!memcmp(x->values,y->values,sizeof x->values),"disc/CUE metadata");
        for (unsigned j=0;j<11;++j)
            check((!x->strings[j]&&!y->strings[j]) || (x->strings[j]&&y->strings[j]&&!strcmp(x->strings[j],y->strings[j])),"all strings");
    }
    check(!aux && !headers,"auxiliary allocation/header cleanup");
    check(new_compares==old_compares,"same comparison sequence length");
    if (n>=4096 && n<=65000 && !failure && !subset) check(new_copies<old_copies,"owning copies reduced");
    deque_destroy(candidate); deque_destroy(original);
    check(!live,"all owning strings released exactly once");
    printf("n=%u mode=%d ties=%d failure=%d subset=%d copies=%u->%u compares=%u cpu_us=%ld->%ld\n",
           n,mode,ties,failure,subset,old_copies,new_copies,new_compares,old_us,new_us);
}
int main(void) {
    check(_type_register(sizeof(record),"stSongInfo",init,song_record_copy,compare_a,destroy),"type registration");
    unsigned sizes[]={0,1,2,15,16,17,63,64,65,128,257,4096,43086,65000,65001};
    for (unsigned mode=0;mode<2;++mode) {
        for (unsigned i=0;i<sizeof sizes/sizeof *sizes;++i) run(sizes[i],mode,0,0,0);
        run(257,mode,1,0,0);
        for (int failure=1;failure<=4;++failure) run(257,mode,0,failure,0);
        run(257,mode,0,0,1);
    }
    printf("Real stock libcstl: exact order/ties, owning strings, metadata, limits, allocation/header failures, scan and subrange fallback passed.\n");
    return 0;
}
'''

build = pathlib.Path(sys.argv[1]).resolve()
qemu = shutil.which('qemu-mipsel')
if not qemu:
    raise SystemExit('qemu-mipsel is required (Arch: pacman -S qemu-user)')
with tempfile.TemporaryDirectory(prefix='q2-reference-sort-') as directory:
    tmp = pathlib.Path(directory)
    runtime = tmp / 'runtime'
    subprocess.run(['unsquashfs', '-no-progress', '-d', str(runtime), str(build/'stock.squashfs'),
                    'lib', 'usr/lib'], check=True, stdout=subprocess.DEVNULL)
    (tmp/'sortkeys_test.h').write_text(HEADER)
    (tmp/'harness.c').write_text(HARNESS)
    flags = [f for f in FLAGS if f not in ('-mno-abicalls', '-G0')] + ['-mnan=2008', '-mabs=2008', '-mabicalls']
    for source, obj in ((ROOT/'patch/sortkeys.c', 'sort.o'), (tmp/'harness.c', 'harness.o')):
        subprocess.run(['clang', *flags, '-DSORT_TEST', '-I', str(tmp), '-c', str(source), '-o', str(tmp/obj)], check=True)
    binary = tmp/'reference-sort'
    subprocess.run(['ld.lld', '-m', 'elf32ltsmip', '-e', '__start', '--dynamic-linker', '/lib/ld-linux-mipsn8.so.1',
                    str(tmp/'sort.o'), str(tmp/'harness.o'), str(build/'start.o'),
                    str(runtime/'usr/lib/libcstl.so.2.2.0'), str(build/'libc-2.28.so'), '-o', str(binary)], check=True)
    subprocess.run([qemu, '-L', str(runtime), str(binary)], check=True)
