# Guest cache ownership by title — 16 October 2026

Original pinned SaveDataFactory::GetFullPath substitutes the current process
ID for guest Account/Device storage requests with title ID zero, but not Cache.
Consequently two titles requesting Cache(0) can share the same save/cache/0
folder, even when their cached binary data is not compatible.

This port keeps the pinned sources untouched and builds a versioned maintained
core file whose sole difference resolves Cache(0) to the running program ID.
Explicit Cache IDs and System/Temporary/Account/Device paths are unchanged.

The CI Clang ASan/UBSan host test compiles the actual GetFullPath method from
both pinned and maintained source, checks that the original reproduces the
shared zero-ID path and the maintained source separates two games, and checks
unchanged explicit IDs and other save types. No native package is built.

Existing old shared cache files are not migrated or deleted. A new per-title
cache may need regeneration. This does not establish FC27 gameplay improvement,
nor does it prove FC27 uses zero-ID cache on the console.

Reference: https://github.com/blackbearreloaded/ProsperoEden/commit/a302cde87a03158bfeab2a37aaf27e772d184b9d
