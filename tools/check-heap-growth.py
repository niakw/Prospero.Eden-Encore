#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Host check of the heap that grows by pieces (headless/heap_arenas.inc).

Builds the app's heap source as headless/CMakeLists.txt derives it and runs it on Linux over a
stand-in for the console's mspace functions: a first-fit allocator with checked block headers.
Eight threads allocate, resize and free blocks of every size, each filled with a pattern that
is checked when the block changes hands, so an owner looked up wrongly, a block handed out
twice or a piece used before it has memory shows as a damaged pattern or header (or a fault:
the range is unreadable until committed). Then the limits: one request larger than a piece, a
large request when the console has no memory for a block of its own, the heap filled to its
3 GiB, and the same run with the range refused (the old whole-heap path).
"""
import pathlib
import platform
import subprocess
import sys
import tempfile

root = pathlib.Path(__file__).resolve().parents[1]
heap = (root / 'third_party/app_heap.c').read_text()
for old, new in (
    ('128 MiB', '3072 MiB'),
    ('(128u * 1024u * 1024u)', '(3072u * 1024u * 1024u)'),
    ('#include <sys/mman.h>', '#include <sys/mman.h>\nvoid *eden_heap_pages(size_t);\nvoid eden_heap_pages_free(void *, size_t);'),
    ('"PS5-OpenGL"', '"Eden-headless"'),
):
    assert old in heap, old
    heap = heap.replace(old, new)
begin = heap.index('static int ps5_heap_ready(void) {')
end = heap.index('void ps5_opengl_heap_stats_print(unsigned iteration) {')
heap = heap[:begin] + (root / 'headless/heap_arenas.inc').read_text() + heap[end:]
for required in (
    '3072 MiB', 'eden_heap_commit', 'eden_heap_pages', 'eden_heap_pages_free',
    'eden_heap_arenas_created', 'eden_heap_committed',
    'eden_heap_tcache_held', 'EDEN_TCACHE_TOTAL_LIMIT',
    '__builtin_ia32_pause',
):
    assert required in heap, f'heap derivation contract changed: {required}'
# Kernel logging is not allowed inside the serial physical-memory growth
# critical section, even on hosts where the logger stub is nonblocking.
growth = heap[heap.index('static int eden_heap_grow(size_t bytes, unsigned seen) {'):
              heap.index('/* A block from the heap', heap.index('static int eden_heap_grow(size_t bytes, unsigned seen) {'))]
assert growth.index('atomic_flag_clear_explicit(&eden_heap_grow_lock, memory_order_release)') < (
    growth.index('eden_heap_log_growth(report_request, report_root'))
assert growth.index('atomic_flag_clear_explicit(&eden_heap_grow_lock, memory_order_release)') < (
    growth.index('eden_heap_grow_refused(report_refusal)'))
assert 'report_refusal = ("EDEN_HEAP_GROW refused:' in growth
assert 'snprintf(' not in growth and 'printf(' not in growth
if platform.machine().lower() not in ('x86_64', 'amd64'):
    print('Heap growth source/derivation contract PASS (x86 UBSan/TSan runtime harness deferred to CI)')
    raise SystemExit(0)

MOCK = r'''
// A stand-in for the console: mspaces over caller memory, and the range the heap grows in.
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define BLOCK_MAGIC 0xb10cb10cb10cb10cull
#define ALIAS_MAGIC 0xa11a5a11a5a11a50ull
struct block { size_t size; uint64_t magic; struct block *next_free; uint64_t used; };  // 32 bytes before the data
struct space { pthread_mutex_t lock; struct block *free_list; char *start, *end; uint64_t magic; };
_Static_assert(sizeof(struct block) == 32, "header");

static int refuse_first_mspace, refuse_growth_mspace;
static unsigned growth_mspace_attempts;
void *sceLibcMspaceCreate(const char *name, void *base, size_t size, unsigned flags) {
    (void)name; (void)flags;
    if (refuse_first_mspace) { refuse_first_mspace = 0; return NULL; }
    if (strcmp(name, "Eden-heap") == 0) {
        ++growth_mspace_attempts;
        if (refuse_growth_mspace) { refuse_growth_mspace = 0; return NULL; }
    }
    assert(size >= 4096 && ((uintptr_t)base & 15) == 0);
    struct space *space = base;
    pthread_mutex_init(&space->lock, NULL);
    space->magic = 0x5bace5bace5bace5ull;
    space->start = (char *)base + 128;
    space->end = (char *)base + size;
    struct block *first = (struct block *)space->start;
    first->size = (size_t)(space->end - space->start) - sizeof(struct block);
    first->magic = BLOCK_MAGIC; first->next_free = NULL; first->used = 0;
    space->free_list = first;
    return space;
}
static struct block *header_of(const void *address) {
    struct block *block = (struct block *)address - 1;
    if (block->magic == ALIAS_MAGIC) block = (struct block *)block->next_free;   // an aligned block: its real header
    if (block->magic != BLOCK_MAGIC) { fprintf(stderr, "damaged block header at %p\n", address); abort(); }
    return block;
}
// Joins neighbouring free blocks (the console's allocator does this as blocks are freed).
static void coalesce(struct space *space) {
    space->free_list = NULL;
    for (char *at = space->start; at < space->end;) {
        struct block *block = (struct block *)at;
        if (block->magic != BLOCK_MAGIC) { fprintf(stderr, "damaged block chain in a space\n"); abort(); }
        if (!block->used) {
            for (;;) {
                struct block *after = (struct block *)((char *)(block + 1) + block->size);
                if ((char *)after >= space->end || after->used) break;
                if (after->magic != BLOCK_MAGIC) { fprintf(stderr, "damaged block chain in a space\n"); abort(); }
                block->size += sizeof(struct block) + after->size;
                after->magic = 0;
            }
            block->next_free = space->free_list;
            space->free_list = block;
        }
        at = (char *)(block + 1) + block->size;
    }
}
static void *take(struct space *space, size_t size) {
    size = (size + 15) & ~(size_t)15;
    if (size < 32) size = 32;
    void *result = NULL;
    pthread_mutex_lock(&space->lock);
    assert(space->magic == 0x5bace5bace5bace5ull);
    for (int attempt = 0; attempt < 2 && result == NULL; ++attempt) {
    if (attempt == 1) coalesce(space);
    for (struct block **link = &space->free_list; *link != NULL; link = &(*link)->next_free) {
        struct block *block = *link;
        assert(block->magic == BLOCK_MAGIC && !block->used);
        if (block->size < size) continue;
        if (block->size >= size + sizeof(struct block) + 64) {
            struct block *rest = (struct block *)((char *)(block + 1) + size);
            rest->size = block->size - size - sizeof(struct block);
            rest->magic = BLOCK_MAGIC; rest->used = 0; rest->next_free = block->next_free;
            block->size = size;
            *link = rest;
        } else {
            *link = block->next_free;
        }
        block->used = 1; block->next_free = NULL;
        result = block + 1;
        break;
    }
    }
    pthread_mutex_unlock(&space->lock);
    return result;
}
void *sceLibcMspaceMalloc(void *space, size_t size) { return take(space, size); }
void *sceLibcMspaceCalloc(void *space, size_t count, size_t size) {
    void *address = take(space, count * size);
    return address ? memset(address, 0, count * size) : NULL;
}
size_t sceLibcMspaceMallocUsableSize(const void *address) {
    const struct block *alias = (const struct block *)address - 1;
    const struct block *block = header_of(address);
    assert(block->used == 1);
    return alias->magic == ALIAS_MAGIC ? alias->size : block->size;
}
void sceLibcMspaceFree(void *handle, void *address) {
    struct space *space = handle;
    struct block *block = header_of(address);
    // The block must lie in the space it is returned to: a wrong owner is the bug this check hunts.
    if ((char *)block < space->start || (char *)block >= space->end || block->used != 1) {
        fprintf(stderr, "block %p freed to a space that does not hold it\n", address); abort();
    }
    pthread_mutex_lock(&space->lock);
    block->used = 0;
    block->next_free = space->free_list;
    space->free_list = block;
    pthread_mutex_unlock(&space->lock);
}
void *sceLibcMspaceRealloc(void *space, void *address, size_t size) {
    const size_t before = sceLibcMspaceMallocUsableSize(address);
    if (size <= before && size != 0) return address;
    if (size == 0) { sceLibcMspaceFree(space, address); return NULL; }
    void *moved = take(space, size);
    if (moved == NULL) return NULL;   // like the console: the caller's block stays
    memcpy(moved, address, before);
    sceLibcMspaceFree(space, address);
    return moved;
}
int sceLibcMspacePosixMemalign(void *space, void **address, size_t alignment, size_t size) {
    if (alignment < sizeof(void *) || (alignment & (alignment - 1)) != 0) return EINVAL;
    if (alignment <= 16) { *address = take(space, size); return *address ? 0 : ENOMEM; }
    char *raw = take(space, size + alignment + sizeof(struct block));
    if (raw == NULL) return ENOMEM;
    char *aligned = (char *)(((uintptr_t)raw + sizeof(struct block) + alignment - 1) & ~(uintptr_t)(alignment - 1));
    struct block *alias = (struct block *)aligned - 1;
    alias->magic = ALIAS_MAGIC; alias->next_free = (struct block *)raw - 1; alias->size = size; alias->used = 1;
    *address = aligned;
    return 0;
}
int sceKernelUsleep(unsigned int microseconds) { return usleep(microseconds); }
static atomic_uint observed_growth_logs;
static atomic_size_t last_growth_request;
static atomic_uint last_growth_root;
static atomic_uint last_growth_span;
int sceKernelDebugOutText(int channel, const char *text) {
    (void)channel;
    if (strncmp(text, "EDEN_HEAP_GROW req_bytes=", 25) == 0) {
        size_t req = 0, pieces = 0, committed_mib = 0;
        unsigned root = 0, spaces = 0;
        assert(sscanf(text,
            "EDEN_HEAP_GROW req_bytes=%zu root=%u pieces=%zu spaces=%u committed_mib=%zu",
            &req, &root, &pieces, &spaces, &committed_mib) == 5);
        /* MOCK precedes the generated allocator definitions in this C TU. */
        assert(root < 24u && pieces > 0 && root + pieces <= 24u);
        assert(spaces > 0 && spaces <= 24u);
        assert(committed_mib == (root + pieces) * 128);
        atomic_store(&last_growth_request, req);
        atomic_store(&last_growth_root, root);
        atomic_store(&last_growth_span, (unsigned)pieces);
        atomic_fetch_add(&observed_growth_logs, 1);
    }
    return (int)write(2, text, strlen(text));
}

// The C library's own allocator, for what the app's heap does not own.
void *__real_malloc(size_t size) { return malloc(size); }
void *__real_calloc(size_t count, size_t size) { return calloc(count, size); }
void *__real_realloc(void *address, size_t size) { return realloc(address, size); }
void __real_free(void *address) { free(address); }
int __real_posix_memalign(void **address, size_t alignment, size_t size) { return posix_memalign(address, alignment, size); }
size_t malloc_usable_size(void *);
size_t __real_malloc_usable_size(const void *address) { return malloc_usable_size((void *)address); }

// The range the heap grows in: unreadable until committed, so a piece used early faults.
static int refuse_range, refuse_first_commit;
static int abandoned_initial_mspace;
static unsigned rolled_back_growth;
static unsigned dense_fallback_attempts;
static void *last_reserved_base;
static size_t last_reserved_size;
static atomic_size_t committed_bytes;
void *eden_heap_reserve(size_t size) {
    if (refuse_range) return NULL;
    void *address = mmap(NULL, size, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    if (address != MAP_FAILED) { last_reserved_base = address; last_reserved_size = size; }
    return address == MAP_FAILED ? NULL : address;
}
int eden_heap_commit(void *address, size_t size) {
    if (refuse_first_commit) { refuse_first_commit = 0; return -1; }
    assert(((uintptr_t)address & 0x1fffff) == 0 && (size & 0x1fffff) == 0);
    if (mprotect(address, size, PROT_READ | PROT_WRITE) != 0) return -1;
    atomic_fetch_add(&committed_bytes, size);
    return 0;
}
int eden_heap_commit_growth(void *address, size_t size, int64_t *physical) {
    assert(physical != NULL);
    *physical = -1; // host anonymous commit has no direct physical owner
    return eden_heap_commit(address, size);
}
void eden_heap_rollback_growth(void *address, size_t size, int64_t physical) {
    assert(physical == -1);
    void *guard = mmap(address, size, PROT_NONE,
                       MAP_FIXED | MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(guard == address);
    const size_t committed = atomic_fetch_sub(&committed_bytes, size);
    assert(committed >= size);
    ++rolled_back_growth;
}
static int refuse_pages;   // the console has no memory left for a block of its own
void *eden_heap_pages(size_t size) {
    if (size == ((size_t)3072 << 20)) ++dense_fallback_attempts;
    if (refuse_pages) return NULL;
    void *address = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    return address == MAP_FAILED ? NULL : address;
}
void eden_heap_pages_free(void *address, size_t size) { munmap(address, size); }
int64_t eden_heap_first_direct_owner(void) { return -1; }
void eden_heap_abandon_initial(void *address, size_t reserved) {
    assert(address == last_reserved_base && reserved == last_reserved_size);
    assert(munmap(address, reserved) == 0);
    atomic_fetch_sub(&committed_bytes, (size_t)128 << 20);
    abandoned_initial_mspace = 1;
}
'''

TEST = r'''
void *__wrap_malloc(size_t);
void *__wrap_calloc(size_t, size_t);
void *__wrap_realloc(void *, size_t);
void __wrap_free(void *);
int __wrap_posix_memalign(void **, size_t, size_t);
size_t __wrap_malloc_usable_size(const void *);
unsigned eden_heap_arenas_created(void);
size_t eden_heap_committed(void);
size_t eden_heap_large_held(unsigned *blocks);

static void fill(unsigned char *block, size_t size, unsigned seed) {
    // The start and the end of a large block are enough to see another owner writing into it.
    for (size_t i = 0; i < size; i = (i == 4095 && size > 8192) ? size - 4096 : i + 1)
        block[i] = (unsigned char)(seed + i * 131u);
}
static void verify(const unsigned char *block, size_t size, unsigned seed) {
    for (size_t i = 0; i < size; i = (i == 4095 && size > 8192) ? size - 4096 : i + 1)
        if (block[i] != (unsigned char)(seed + i * 131u)) { fprintf(stderr, "pattern damaged at %p+%zu\n", (void *)block, i); abort(); }
}
struct held { unsigned char *block; size_t size; unsigned seed; };
static atomic_ulong operations;
static void *worker(void *argument) {
    unsigned state = (unsigned)(uintptr_t)argument * 2654435761u + 1;
    enum { SLOTS = 200 };
    struct held held[SLOTS] = {0};
    for (int round = 0; round < 60000; ++round) {
        state = state * 1664525u + 1013904223u;
        struct held *slot = &held[(state >> 8) % SLOTS];
        const unsigned kind = (state >> 20) % 1000;
        size_t size = kind < 700 ? 1 + (state >> 4) % 2000              // small: the thread's arena
                    : kind < 930 ? 4096 + (state >> 4) % 400000          // medium: arena or the spaces
                    : kind < 997 ? 300000 + (size_t)(state >> 4) % 6000000
                                 : 20000000 + (size_t)(state >> 4) % 40000000;
        if (slot->block == NULL) {
            const unsigned how = (state >> 28) % 4;
            if (how == 0) {
                slot->block = __wrap_calloc(1, size);
                if (slot->block) for (size_t i = 0; i < size && i < 4096; ++i) assert(slot->block[i] == 0);
            } else if (how == 1) {
                void *address = NULL;
                const size_t alignment = (size_t)64 << ((state >> 12) % 8);
                if (__wrap_posix_memalign(&address, alignment, size) == 0) {
                    assert(((uintptr_t)address & (alignment - 1)) == 0);
                    slot->block = address;
                }
            } else {
                slot->block = __wrap_malloc(size);
            }
            if (slot->block == NULL) continue;   // the heap is full for this size right now
            assert(__wrap_malloc_usable_size(slot->block) >= size);
            slot->size = size; slot->seed = state;
            fill(slot->block, size, slot->seed);
        } else if ((state >> 30) & 1) {
            verify(slot->block, slot->size, slot->seed);
            unsigned char *moved = __wrap_realloc(slot->block, size);
            if (moved == NULL) continue;         // the old block stays
            // The start came along (the pattern covers a block's first and last 4096 bytes, so
            // only its start is known at the new size).
            const size_t kept = size < slot->size ? size : slot->size;
            verify(moved, kept < 4096 ? kept : 4096, slot->seed);
            slot->block = moved; slot->size = size; slot->seed = state;
            fill(moved, size, slot->seed);
        } else {
            verify(slot->block, slot->size, slot->seed);
            __wrap_free(slot->block);
            slot->block = NULL;
        }
        atomic_fetch_add(&operations, 1);
    }
    for (int i = 0; i < SLOTS; ++i)
        if (held[i].block) { verify(held[i].block, held[i].size, held[i].seed); __wrap_free(held[i].block); }
    return NULL;
}

int main(int argc, char **argv) {
    refuse_range = argc > 1 && strcmp(argv[1], "whole") == 0;
    const size_t piece = (size_t)128 << 20, heap = (size_t)3072 << 20;
    if (argc > 1 && strcmp(argv[1], "first-mspace-fail") == 0) {
        refuse_first_mspace = 1;
        void *fallback = __wrap_malloc(100);
        assert(fallback != NULL);
        assert(atomic_load(&ps5_heap_state) == -1);
        assert(abandoned_initial_mspace == 1);
        assert(eden_heap_committed() == 0 && atomic_load(&committed_bytes) == 0);
        assert(dense_fallback_attempts == 0);
        unsigned char residency = 0;
        errno = 0;
        assert(mincore(last_reserved_base, 4096, &residency) == -1 && errno == ENOMEM);
        __wrap_free(fallback);
        puts("first-mspace-fail: initial physical backing + VA released PASS");
        return 0;
    }
    if (argc > 1 && strcmp(argv[1], "first-commit-fail") == 0) {
        refuse_first_commit = 1;
        void *fallback = __wrap_malloc(100);
        assert(fallback != NULL);
        assert(atomic_load(&ps5_heap_state) == -1);
        assert(eden_heap_committed() == 0);
        assert(dense_fallback_attempts == 0);
        assert(last_reserved_base != NULL && last_reserved_size == heap);
        unsigned char residency = 0;
        errno = 0;
        assert(mincore(last_reserved_base, 4096, &residency) == -1 && errno == ENOMEM);
        __wrap_free(fallback);
        puts("first-commit-fail: reserved VA released, no dense retry PASS");
        return 0;
    }
    void *first = __wrap_malloc(100);
    assert(first != NULL);
    if (!refuse_range) {
        // It starts with one piece, not the whole heap.
        assert(eden_heap_committed() == piece && atomic_load(&committed_bytes) == piece);
        assert(__wrap_posix_memalign(&first, 24, 100) == EINVAL && eden_heap_committed() == piece);
    } else {
        assert(eden_heap_committed() == heap && atomic_load(&committed_bytes) == 0);
    }
    if (argc == 1) {
        // A size-zero realloc must have deterministic ownership semantics,
        // not silently leave the block count and retained direct RAM unknown.
        void *small_zero = __wrap_malloc(96);
        assert(small_zero != NULL);
        assert(__wrap_realloc(small_zero, 0) == NULL);
        assert(atomic_load(&ps5_heap_ambiguous_zero_reallocs) == 0);
        void *medium_zero = __wrap_malloc((size_t)1 << 20);
        assert(medium_zero != NULL);
        assert(__wrap_realloc(medium_zero, 0) == NULL);
        const size_t big_bytes = (size_t)40 << 20;
        unsigned big_blocks = 0;
        void *large_zero = __wrap_malloc(big_bytes);
        assert(large_zero != NULL);
        assert(eden_heap_large_held(&big_blocks) >= big_bytes && big_blocks >= 1);
        assert(__wrap_realloc(large_zero, 0) == NULL);
        assert(eden_heap_large_held(&big_blocks) == 0 && big_blocks == 0);
        assert(atomic_load(&ps5_heap_ambiguous_zero_reallocs) == 0);
    }
    if (argc > 1 && strcmp(argv[1], "title-cycles") == 0) {
        // A closed title must be able to reuse existing, still-physically-
        // backed mspace roots. Physical ownership MUST remain stable across
        // repeated same-sized title sessions, even with the permanent
        // 8-MiB thread-arena pin and the launcher allocation still alive.
        // Do not fake physical reclaim: assert committed bytes stay retained.
        enum { SESSION_BLOCKS = 8, SESSION_COUNT = 7 };
        void *blocks[SESSION_BLOCKS];
        size_t plateau = 0;
        for (unsigned cycle = 0; cycle < SESSION_COUNT; ++cycle) {
            for (unsigned i = 0; i < SESSION_BLOCKS; ++i) {
                blocks[i] = __wrap_malloc((size_t)24 << 20);
                assert(blocks[i] != NULL);
                ((unsigned char *)blocks[i])[0] = (unsigned char)(i + cycle);
                ((unsigned char *)blocks[i])[((size_t)24 << 20) - 1] =
                    (unsigned char)(cycle ^ i);
            }
            for (unsigned i = 0; i < SESSION_BLOCKS; ++i) {
                assert(((unsigned char *)blocks[i])[0] == (unsigned char)(i + cycle));
                __wrap_free(blocks[i]);
            }
            const size_t committed = eden_heap_committed();
            assert(committed >= 2 * piece && committed <= heap);
            (void)eden_heap_release_current_tcache();
            assert(eden_heap_committed() == committed);
            if (cycle == 0) plateau = committed;
            else assert(committed == plateau);
        }
        // This is safe REUSE, not a claim that root mspaces were destroyed.
        // Child arena pins must survive until actual owning allocator exit.
        assert(atomic_load(&eden_heap_root_arena_pins[0]) >= 1);
        assert(atomic_load(&committed_bytes) == plateau);
        assert(eden_heap_committed() == plateau);
        __wrap_free(first);
        puts("title-cycles: 7 sessions reuse same physical backing without growth, no unsafe unmap PASS");
        return 0;
    }
    if (argc > 1 && strcmp(argv[1], "root-span") == 0) {
        // If a direct large allocation cannot be admitted, a request larger
        // than one piece must create ONE root mspace across multiple pieces.
        refuse_pages = 1;
        unsigned char *block = __wrap_malloc(piece + piece / 2);
        refuse_pages = 0;
        assert(block != NULL);
        assert(eden_heap_committed() == 3 * piece);
        assert(eden_heap_root_span[1] == 2);
        assert(atomic_load(&observed_growth_logs) == 1);
        assert(atomic_load(&last_growth_request) == piece + piece / 2);
        assert(atomic_load(&last_growth_root) == 1);
        assert(atomic_load(&last_growth_span) == 2);
        assert(atomic_load(&eden_heap_piece_root[1]) == 1);
        assert(atomic_load(&eden_heap_piece_root[2]) == 1);
        assert(eden_heap_root_direct_owner[1] == -1);
        eden_heap_flush(eden_heap_self());
        assert(atomic_load(&eden_heap_root_held_blocks[1]) == 1);
        assert(atomic_load(&eden_heap_root_held_bytes[1]) >= (long)(piece + piece / 2));
        __wrap_free(block);
        __wrap_free(first);
        (void)eden_heap_release_current_tcache();
        assert(atomic_load(&eden_heap_root_held_blocks[1]) == 0);
        assert(atomic_load(&eden_heap_root_held_bytes[1]) == 0);
        assert(eden_heap_committed() == 3 * piece); // NEVER unmap a root from a counter
        assert(atomic_load(&eden_heap_root_arena_pins[0]) >= 1);
        puts("root-span: multi-piece PA owner, physical counters and no unsafe release PASS");
        return 0;
    }
    if (argc > 1 && strcmp(argv[1], "growth-mspace-fail") == 0) {
        // The main thread's small allocation first creates an 8 MiB
        // aligned arena in the same 128 MiB piece. The alignment and
        // allocator metadata mean FOUR 30 MiB blocks cannot fit there.
        // Keep three 30 MiB allocations in the initial piece, then make
        // the fourth trigger growth with a deliberate mspace failure.
        void *retained[3];
        for (int i = 0; i < 3; ++i) {
            retained[i] = __wrap_malloc((size_t)30 << 20);
            assert(retained[i] != NULL);
        }
        assert(eden_heap_committed() == piece);
        refuse_growth_mspace = 1;
        assert(__wrap_malloc((size_t)30 << 20) == NULL);
        assert(growth_mspace_attempts == 1);
        assert(rolled_back_growth == 1);
        assert(eden_heap_committed() == piece);
        assert(atomic_load(&committed_bytes) == piece);
        // MAP_FIXED restored a guard without breaking the surrounding 3 GiB VA.
        // It must also discard the failed page's previously touched residency.
        unsigned char residency = 0xff;
        assert(mincore((char *)last_reserved_base + piece, 4096, &residency) == 0);
        assert((residency & 1) == 0);
        for (int i = 0; i < 12; ++i) {
            // No second mspace attempt/committed piece, even after a
            // transient failure flag is cleared by the mock.
            assert(__wrap_malloc((size_t)30 << 20) == NULL);
            assert(eden_heap_committed() == piece);
        }
        assert(growth_mspace_attempts == 1);
        assert(rolled_back_growth == 1);
        assert(atomic_load(&committed_bytes) == piece);
        // All healthy older mspaces still serve small allocations.
        void *small = __wrap_malloc(1024);
        assert(small != NULL);
        __wrap_free(small);
        for (int i = 0; i < 3; ++i) __wrap_free(retained[i]);
        __wrap_free(first);
        puts("growth-mspace-fail: failed 128 MiB backing returned, VA guarded, no repeat, old mspace usable PASS");
        return 0;
    }
    // A single thread frees ~4 MiB in many size classes. Its private
    // free-list must keep <=1 MiB; the excess goes back to the mspaces.
    enum { TCACHE_PRESSURE = 4096 };
    void *cache_pressure[TCACHE_PRESSURE];
    for (int i = 0; i < TCACHE_PRESSURE; ++i) {
        cache_pressure[i] = __wrap_malloc(16u * (1u + (unsigned)i % 127u));
        assert(cache_pressure[i] != NULL);
    }
    for (int i = 0; i < TCACHE_PRESSURE; ++i)
        __wrap_free(cache_pressure[i]);
    assert(eden_heap_tcache_held() <= ((size_t)1 << 20));
    // Reuse the surviving hot cache; the bounded accounting must never underflow.
    for (int i = 0; i < TCACHE_PRESSURE; ++i) {
        void *block = __wrap_malloc(16u * (1u + (unsigned)i % 127u));
        assert(block != NULL);
        __wrap_free(block);
    }
    assert(eden_heap_tcache_held() <= ((size_t)1 << 20));
    pthread_t threads[8];
    for (uintptr_t i = 0; i < 8; ++i) assert(pthread_create(&threads[i], NULL, worker, (void *)(i + 1)) == 0);
    for (int i = 0; i < 8; ++i) pthread_join(threads[i], NULL);
    // Joined workers have flushed their private caches at TLS destruction.
    // Only this main thread can still retain its <=1 MiB hot free-list.
    assert(eden_heap_tcache_held() <= ((size_t)1 << 20));
    // Title-switch maintenance may drain only this thread's own freed blocks.
    // It may not deallocate an mspace or shrink direct physical backing.
    const size_t heap_before_drain = eden_heap_committed();
    // The cache's logical blocks are freed but remain physically held.
    // Their release must debit exactly the cached usable bytes from the
    // root ledger, while leaving the physical 128-MiB mspace committed.
    eden_heap_flush(eden_heap_self());
    long phys_before_drain = 0;
    for (unsigned root=0; root<EDEN_HEAP_PIECES; ++root)
        phys_before_drain += atomic_load(&eden_heap_root_held_bytes[root]);
    // The old title's hot-space hint must not scatter the next title into
    // a later mspace when earlier committed spaces can be reused.
    atomic_store(&eden_heap_space_hint, EDEN_HEAP_PIECES - 1);
    const size_t freed_cache = eden_heap_release_current_tcache();
    assert(atomic_load(&eden_heap_space_hint) == 0);
    /* A runner/launcher can have no TLS record: even then, the next title
     * must not inherit a stale last-root preference from guest workers.
     * Save/restore the record without invalidating its registered slot. */
    struct eden_heap_thread *original_tls = pthread_getspecific(eden_heap_arena_key);
    assert(original_tls != NULL);
    assert(pthread_setspecific(eden_heap_arena_key, NULL) == 0);
    atomic_store(&eden_heap_space_hint, EDEN_HEAP_PIECES - 1);
    assert(eden_heap_release_current_tcache() == 0);
    assert(atomic_load(&eden_heap_space_hint) == 0);
    assert(pthread_setspecific(eden_heap_arena_key, original_tls) == 0);
    long phys_after_drain = 0;
    for (unsigned root=0; root<EDEN_HEAP_PIECES; ++root)
        phys_after_drain += atomic_load(&eden_heap_root_held_bytes[root]);
    assert(phys_before_drain - phys_after_drain == (long)freed_cache);
    assert(freed_cache <= ((size_t)1 << 20));
    assert(eden_heap_tcache_held() == 0);
    assert(eden_heap_committed() == heap_before_drain);
    // The allocator remains immediately reusable after the drain.
    void *next_title_alloc = __wrap_malloc(128);
    assert(next_title_alloc != NULL);
    __wrap_free(next_title_alloc);
    const size_t after_threads = eden_heap_committed();
    const size_t peak = atomic_load(&ps5_heap_peak_bytes);
    assert(eden_heap_arenas_created() >= 8);
    if (!refuse_range) {
        // It grew, by exactly what was committed. How far depends on how the threads interleave and
        // on this stand-in allocator, which packs blocks far less tightly than the console's: the
        // limit itself is a valid outcome here (requests then fail, and the workers carry on).
        if (!(after_threads > piece && after_threads <= heap && atomic_load(&committed_bytes) == after_threads)) {
            fprintf(stderr, "pieces %zu MiB, committed %zu MiB, most in use %zu MiB\n", after_threads >> 20,
                    atomic_load(&committed_bytes) >> 20, peak >> 20);
            abort();
        }
        // A large block has memory of its own: the heap's pieces do not grow, and it is given
        // back when freed. It can grow in place of nothing: a resize moves it.
        unsigned blocks_alive = 99;
        assert(eden_heap_large_held(&blocks_alive) == 0 && blocks_alive == 0);
        unsigned char *large = __wrap_malloc(5 * piece / 2);
        assert(large != NULL && eden_heap_committed() == after_threads);
        assert(eden_heap_large_held(&blocks_alive) == 5 * piece / 2 && blocks_alive == 1);
        // A live direct-owned large block must always remain Bloom-positive.
        // Other libc objects must continue to route to libc without scanning
        // all 256 direct-block slots on every foreign free/realloc.
        assert(eden_heap_large_maybe((uintptr_t)large));
        unsigned definitely_foreign = 0;
        for (unsigned attempt = 0; attempt < 1000; ++attempt) {
            void *foreign = __real_malloc(1024 + attempt % 64);
            assert(foreign != NULL);
            if (!eden_heap_large_maybe((uintptr_t)foreign)) ++definitely_foreign;
            foreign = __wrap_realloc(foreign, 2048 + attempt % 128);
            assert(foreign != NULL);
            __wrap_free(foreign);
            assert(eden_heap_large_maybe((uintptr_t)large));
        }
        assert(definitely_foreign > 0);
        assert(__wrap_malloc_usable_size(large) == 5 * piece / 2);
        fill(large, 5 * piece / 2, 7);
        verify(large, 5 * piece / 2, 7);
        assert(__wrap_realloc(large, 2 * piece) == large);           // still most of it: it stays
        unsigned char *grown = __wrap_realloc(large, 3 * piece);      // larger: moved, the start kept
        assert(grown != NULL);
        verify(grown, 4096, 7);
        unsigned char *shrunk = __wrap_realloc(grown, 1000);          // small again: into an arena
        assert(shrunk != NULL && eden_heap_large_held(&blocks_alive) == 0 && blocks_alive == 0);
        verify(shrunk, 1000 < 4096 ? 1000 : 4096, 7);
        unsigned char *back = __wrap_realloc(shrunk, (size_t)40 << 20); // and out of the range again
        assert(back != NULL && eden_heap_large_held(&blocks_alive) == ((size_t)40 << 20));
        verify(back, 1000, 7);
        __wrap_free(back);
        assert(eden_heap_large_held(&blocks_alive) == 0 && eden_heap_committed() == after_threads);
        void *aligned = NULL;
        assert(__wrap_posix_memalign(&aligned, 4096, (size_t)33 << 20) == 0 && ((uintptr_t)aligned & 4095) == 0);
        assert(eden_heap_large_held(&blocks_alive) == ((size_t)33 << 20));
        __wrap_free(aligned);
        assert(__wrap_posix_memalign(&aligned, (size_t)1 << 22, (size_t)33 << 20) == 0 && ((uintptr_t)aligned & (((size_t)1 << 22) - 1)) == 0);
        assert(eden_heap_large_held(&blocks_alive) == 0);            // an alignment only a space can give
        __wrap_free(aligned);
        // With no memory left for a block of its own, a large request takes room in the heap.
        refuse_pages = 1;
        unsigned char *inside = __wrap_malloc((size_t)40 << 20);
        refuse_pages = 0;
        assert(inside != NULL && eden_heap_large_held(&blocks_alive) == 0 && blocks_alive == 0);
        fill(inside, (size_t)40 << 20, 9);
        unsigned char *outside = __wrap_realloc(inside, (size_t)48 << 20); // memory is back: moved out
        assert(outside != NULL && eden_heap_large_held(&blocks_alive) == ((size_t)48 << 20));
        verify(outside, 4096, 9);
        __wrap_free(outside);
        assert(eden_heap_large_held(&blocks_alive) == 0 && blocks_alive == 0);
    }
    // Fill the heap with blocks under the large size: the limit is its 3 GiB, and running out
    // returns NULL without damage.
    enum { MANY = 4096 };
    static unsigned char *blocks[MANY];
    int count = 0;
    while (count < MANY && (blocks[count] = __wrap_malloc((size_t)24 << 20)) != NULL) {
        fill(blocks[count], (size_t)24 << 20, (unsigned)count);
        ++count;
    }
    assert(count > 20 && count < MANY && eden_heap_committed() <= heap);
    assert(__wrap_malloc((size_t)-1 - 4096) == NULL);
    // If adding mspace metadata fits but rounding to 128 MiB overflows,
    // no zero-piece heap growth is allowed.
    assert(__wrap_malloc((size_t)-1 - ((size_t)64 << 20)) == NULL);
    void *unaligned = NULL;
    assert(__wrap_posix_memalign(&unaligned, 4096, (size_t)-1 - 8192) != 0);
    // Alignment + request overflow must be rejected before calling mspace.
    assert(__wrap_posix_memalign(&unaligned, (size_t)1 << (sizeof(size_t) * 8 - 1),
                                (size_t)-1 - 1) == ENOMEM);
    for (int i = 0; i < count; ++i) { verify(blocks[i], (size_t)24 << 20, (unsigned)i); __wrap_free(blocks[i]); }
    // After that, everything still works.
    unsigned char *again = __wrap_malloc(1000);
    assert(again != NULL);
    fill(again, 1000, 3); verify(again, 1000, 3);
    __wrap_free(again);
    __wrap_free(first);
    // Worker TLS destructors have returned physical cache entries and the
    // main thread now drains its own. A root can still be pinned by a child
    // arena, but no individual application mspace block may remain live.
    // Realloc across large/direct/root and cache take/keep must balance.
    (void)eden_heap_release_current_tcache();
    long held_blocks = 0, held_bytes = 0;
    unsigned arena_pins = 0;
    for (unsigned root = 0; root < EDEN_HEAP_PIECES; ++root) {
        if (!eden_heap_root_span[root]) continue;
        assert(eden_heap_root_direct_owner[root] == -1);
        const long blocks = atomic_load(&eden_heap_root_held_blocks[root]);
        const long bytes = atomic_load(&eden_heap_root_held_bytes[root]);
        assert(blocks >= 0 && bytes >= 0);
        held_blocks += blocks;
        held_bytes += bytes;
        arena_pins += atomic_load(&eden_heap_root_arena_pins[root]);
    }
    assert(held_blocks == 0 && held_bytes == 0);
    assert(arena_pins >= 1); // the arena still pins its parent's root
    eden_heap_report_roots("host_after_free");
    printf("%s: %lu operations on 8 threads, %u arenas, most in use at once %zu MiB, %zu MiB of pieces after the threads, "
           "%zu MiB when full (%d blocks of 24 MiB)\n",
           refuse_range ? "whole heap at once" : "heap by pieces", atomic_load(&operations), eden_heap_arenas_created(),
           peak >> 20, after_threads >> 20, eden_heap_committed() >> 20, count);
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='eden-heap-') as work:
    work = pathlib.Path(work)
    source = work / 'heap.c'
    source.write_text(MOCK + heap + TEST)
    for flags, label in ((['-O1', '-g', '-fsanitize=undefined', '-fno-sanitize-recover=all'], 'checked'),
                         (['-O2', '-fsanitize=thread'], 'thread sanitizer')):
        binary = work / ('heap-' + label.split()[0])
        subprocess.run(['clang-18', '-std=gnu11', '-pthread', '-Wall', '-Wextra', '-Wno-unused-function',
                        '-Wno-unused-parameter', *flags, str(source), '-o', str(binary)], check=True)
        for mode in ((), ('whole',), ('first-commit-fail',), ('first-mspace-fail',), ('growth-mspace-fail',), ('root-span',), ('title-cycles',)):
            if label != 'checked' and mode:
                continue
            result = subprocess.run([str(binary), *mode], capture_output=True, text=True, timeout=900)
            sys.stdout.write(f'[{label}] ' + result.stdout)
            if result.returncode != 0:
                sys.stderr.write(result.stderr[-3000:])
                sys.exit(f'heap check failed ({label} {" ".join(mode)}): exit {result.returncode}')
print('Heap by pieces: growth on demand, owners by address, requests larger than a piece, the 3 GiB limit, '
      'the whole-heap fallback, first-piece OOM rollback, and eight threads under the thread sanitizer PASS')
