// PS5 x64: retain the storage ABI used by generated monitor operations and
// the original exchange + full-fence unlock ordering. No executable helper
// allocation or call_once is needed for compiler-provided lock-free atomics.
static_assert(__atomic_always_lock_free(sizeof(int), nullptr));
extern "C" int sceKernelUsleep(unsigned int);

void SpinLock::Lock() noexcept {
    unsigned spins = 0;
    while (__atomic_exchange_n(&storage, 1, __ATOMIC_SEQ_CST)) {
        // Poll without repeatedly invalidating the owner's cache line. Guest CPU threads run at
        // critical priority; if an owner is preempted, an unbounded busy waiter can starve it.
        while (__atomic_load_n(&storage, __ATOMIC_RELAXED)) {
            if (++spins < 4096)
                __builtin_ia32_pause();
            else
                sceKernelUsleep(50);
        }
    }
}

void SpinLock::Unlock() noexcept {
    __atomic_exchange_n(&storage, 0, __ATOMIC_SEQ_CST);
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
}
