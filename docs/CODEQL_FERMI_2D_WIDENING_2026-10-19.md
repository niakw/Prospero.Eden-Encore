# CodeQL — Fermi2D pitch address widening (#55, #56)

Branch: `dev/ps5-sparse-jit`. Reviewed: 2026-10-19.

Two CodeQL high-severity C++ alerts report a multiplication performed in a
narrower type before conversion to the 64-bit source address:

- [#55](https://github.com/niakw/Prospero.Eden-Encore/security/code-scanning/55):
  `fermi_2d_observed.cpp` (native default, V81).
- [#56](https://github.com/niakw/Prospero.Eden-Encore/security/code-scanning/56):
  `fermi_2d_experimental.cpp` (experimental, V82, OFF by default).

The old expression `src.Address() + config.src_x0 * bytes_per_pixel`
may discard high multiplication bits before the 64-bit address addition.
The canonical pinned Eden source stays untouched.

Both maintained variants now widen **both operands before multiplication**
to `u64`, guard against overflowing the final 64-bit guest address, and
reject that operation through the existing fail-soft path without mutating
the temporary source descriptor. Pitch alignment also guards a zero
`bytes_per_pixel` before division. All ordinary address semantics and
the existing OFF-by-default experimental selector remain unchanged.

`tools/check-maintained-fermi2d-variants.py` reconstructs the pinned
baseline with the explicit security-only replacement, then verifies
exact maintained-default and optional-experimental parity, preserving
the three historical experimental edits.

`tools/check-fermi2d-address-widening-host.py` compiles the extracted
actual address-alignment block with Clang ASan/UBSan and verifies a
carry into the upper address word, a previously truncated large product,
rejection of 64-bit address wrap, zero block size, and unchanged
non-alignment cases.

The host CI and the C/C++ CodeQL advanced scan must pass for the **same
commit** before considering the two findings resolved. GitHub alert
states should then be checked separately; a passing workflow alone
does not prove that either alert changed state. This is not a native
console execution test or a GPU performance improvement claim.
