// SPDX-License-Identifier: GPL-3.0-or-later
// Detailed-logging-only, bounded, buffered audit of network *API* events.
// This does not intercept, reroute, override or configure any system DNS.
#include "network_audit.h"
#include <pthread.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

enum { MAX_PATH=768, MAX_LOG=4*1024*1024, BUFFER_SIZE=32768 };
static pthread_mutex_t audit_mutex = PTHREAD_MUTEX_INITIALIZER;
static atomic_int audit_enabled = ATOMIC_VAR_INIT(0);
static char audit_path[MAX_PATH], audit_old[MAX_PATH + 12];
static char audit_buffer[BUFFER_SIZE];
static FILE* audit_file;
static unsigned long long audit_bytes;
static unsigned audit_line_count;
// Repeated guest DNS refusals must not serialize thousands of identical writes
// through this diagnostic logger. The network policy executes independently,
// before this call; only the *audit* of duplicate denied requests is folded.
// Exact events and all accepted native/guest packets retain their usual logs.
static atomic_uint_fast64_t denied_epoch_hash = ATOMIC_VAR_INIT(0);
static atomic_ullong denied_suppressed = ATOMIC_VAR_INIT(0);

// Only on the optional audit writer. Existing Unix epoch stays for backwards
// compatibility; UTC is human-readable and mono_ns correlates with native
// CPU/GPU clocks. Never read either clock when Detailed Logging is OFF.
static void audit_timestamp(char utc[32], long long* epoch, long long* mono_ns) {
    struct timespec real = {0, 0};
    struct timespec mono = {0, 0};
    if (clock_gettime(CLOCK_REALTIME, &real) != 0)
        real.tv_sec = time(NULL);
    const int monotonic_ok = clock_gettime(CLOCK_MONOTONIC, &mono) == 0;
    *epoch = (long long)real.tv_sec;
    *mono_ns = monotonic_ok ?
        (long long)mono.tv_sec * 1000000000LL + (long long)mono.tv_nsec : -1LL;
    struct tm converted = {0};
    if (gmtime_r(&real.tv_sec, &converted)) {
        (void)snprintf(utc, 32, "%04d-%02d-%02dT%02d:%02d:%02d.%03ldZ",
            converted.tm_year + 1900, converted.tm_mon + 1, converted.tm_mday,
            converted.tm_hour, converted.tm_min, converted.tm_sec,
            real.tv_nsec / 1000000L);
    } else {
        (void)snprintf(utc, 32, "unknown");
    }
}


static void flush_denied_summary_locked(void) {
    const unsigned long long skipped = atomic_exchange_explicit(
        &denied_suppressed, 0, memory_order_relaxed);
    if (!audit_file || !skipped) return;
    char utc[32];
    long long epoch = 0, mono_ns = -1;
    audit_timestamp(utc, &epoch, &mono_ns);
    // A summary records the time it was flushed, NOT a fabricated original
    // timestamp for each suppressed denial. Keep the same schema as events.
    const int count = fprintf(audit_file,
        "epoch=%lld utc=%s mono_ns=%lld scope=guest event=dns-denied-summary target=aggregated bytes=0 status=0 count=%llu\n",
        epoch, utc, mono_ns, skipped);
    if (count > 0) audit_bytes += (unsigned)count;
}

static uint32_t audit_host_hash(const char* host, int status) {
    uint32_t h = UINT32_C(2166136261) ^ (uint32_t)status;
    for (const unsigned char* p=(const unsigned char*)host; *p; ++p)
        h = (h ^ *p) * UINT32_C(16777619);
    return h;
}

static void close_locked(void) {
    if (audit_file) {
        flush_denied_summary_locked();
        (void)fflush(audit_file);
        (void)fclose(audit_file);
        audit_file = NULL;
    }
    audit_bytes=0;
    audit_line_count=0;
}
static void open_locked(void) {
    if (!audit_path[0] || audit_file) return;
    // Before opening a new file, roll over stale logs from past sessions.
    FILE* existing=fopen(audit_path,"rb");
    long old_size=0;
    if (existing) {
        if (!fseek(existing,0,SEEK_END)) old_size=ftell(existing);
        fclose(existing);
    }
    if (old_size < 0) old_size=0;
    if (old_size >= MAX_LOG) {
        (void)remove(audit_old);
        (void)rename(audit_path,audit_old);
        old_size=0;
    }
    audit_file=fopen(audit_path,"ab");
    if (audit_file) {
        (void)setvbuf(audit_file,audit_buffer,_IOFBF,sizeof(audit_buffer));
        audit_bytes=(unsigned long long)old_size;
    }
}
int eden_network_audit_init(const char* path, int detailed) {
    if (!path) return -1;
    const size_t n=strlen(path);
    if (!n || n+6 >= sizeof(audit_path)) return -1;
    pthread_mutex_lock(&audit_mutex);
    if (audit_path[0]) { pthread_mutex_unlock(&audit_mutex); return -1; }
    memcpy(audit_path,path,n+1);
    snprintf(audit_old,sizeof(audit_old),"%s.prev",path);
    // No normal log file when Detailed Logging is OFF. Keep separate crash-*.
    if (!detailed) { (void)remove(audit_path); (void)remove(audit_old); }
    atomic_store_explicit(&audit_enabled,detailed!=0,memory_order_release);
    pthread_mutex_unlock(&audit_mutex);
    return 0;
}
int eden_network_audit_active(void) {
    return atomic_load_explicit(&audit_enabled,memory_order_relaxed);
}
void eden_network_audit_enable(int detailed) {
    pthread_mutex_lock(&audit_mutex);
    if (!detailed) atomic_store_explicit(&audit_enabled,0,memory_order_release);
    if (!detailed) close_locked();
    if (detailed && audit_path[0])
        atomic_store_explicit(&audit_enabled,1,memory_order_release);
    pthread_mutex_unlock(&audit_mutex);
}
static void safe_token(const char* s, char* out, size_t n) {
    size_t i=0;
    if (!s) s="-";
    for (;*s && i+1<n;++s) {
        const unsigned char c=(unsigned char)*s;
        out[i++]=(c>=33 && c<=126 && c!='"' && c!='\\') ? (char)c : '_';
    }
    out[i]=0;
}
void eden_network_audit_event(const char* scope, const char* event,
                              const char* target, unsigned long long bytes,
                              int status) {
    if (!atomic_load_explicit(&audit_enabled,memory_order_acquire)) return;
    if (scope && event && target && strcmp(scope,"guest")==0 &&
        strcmp(event,"dns-denied")==0) {
        const uint64_t key = ((uint64_t)(uint32_t)time(NULL) << 32) |
                             audit_host_hash(target,status);
        // Lock-free common path: at most one verbatim identical denial per
        // second per dominant domain. Hash collisions affect only diagnostic
        // compression, never actual DNS answers or domain-policy matches.
        if (atomic_exchange_explicit(&denied_epoch_hash, key,
                                     memory_order_relaxed) == key) {
            atomic_fetch_add_explicit(&denied_suppressed, 1,
                                      memory_order_relaxed);
            return;
        }
    }
    pthread_mutex_lock(&audit_mutex);
    if (!atomic_load_explicit(&audit_enabled,memory_order_relaxed)) {
        pthread_mutex_unlock(&audit_mutex);
        return;
    }
    open_locked();
    if (audit_file) {
        flush_denied_summary_locked();
        char sc[24],kind[28],dst[256];
        safe_token(scope,sc,sizeof(sc));
        safe_token(event,kind,sizeof(kind));
        safe_token(target,dst,sizeof(dst));
        char utc[32];
        long long epoch = 0, mono_ns = -1;
        audit_timestamp(utc, &epoch, &mono_ns);
        const int count=fprintf(audit_file,
            "epoch=%lld utc=%s mono_ns=%lld scope=%s event=%s target=%s bytes=%llu status=%d\n",
            epoch,utc,mono_ns,sc,kind,dst,bytes,status);
        if (count > 0) audit_bytes+=(unsigned)count;
        if (++audit_line_count >= 64) {
            // Buffer output: periodic fflush for forensic usefulness; no
            // fsync-per-packet and no quiet-mode cost.
            (void)fflush(audit_file);
            audit_line_count=0;
        }
        if (audit_bytes >= MAX_LOG) {
            close_locked();
            (void)remove(audit_old);
            (void)rename(audit_path,audit_old);
        }
    }
    pthread_mutex_unlock(&audit_mutex);
}
