# Filesystem access (sandbox elevation)

Encore keeps the self-contained ProsperoEden 1.000.040 elevation design instead of adopting the
newer Lapy path.

The implementation originates from
[ps5-native-app-boilerplate](https://github.com/blackbearreloaded/ps5-native-app-boilerplate)
`examples/sandbox-elevation` at `dd44bbd` (GPL-3.0-or-later): `elevation.hpp`,
`protocol.hpp`, `elevation.cpp`, `helper/` and `validate-helper.py`.

## Encore target

- Application title ID: `PPSA99008`.
- Primary validated firmware target: **PS5 13.60**.
- Requested capability: `Capability::filesystem`.
- Helper packaged as `/app0/sandbox-elevator.elf`.
- The request is made once during single-threaded startup.
- Without a usable local ELF loader/elevation path, the request fails and the application stays
  sandboxed instead of treating elevation as successful.

Other firmware versions are not claimed as validated by Encore until tested on hardware.

## Security properties

This path is intentionally one-shot and narrow at the protocol boundary:

1. The application connects only to the local ELF-loader endpoint at `127.0.0.1:9021`.
2. Socket connect/send/receive operations use bounded five-second timeouts.
3. The protocol is a fixed 24-byte little-endian structure with magic, version, kind, capability,
   PID and status validation.
4. Only `Capability::filesystem` is accepted. Arbitrary privilege masks, addresses and kernel
   pointers are not supplied by the application.
5. The helper validates the requested PID against the exact PS5 title ID `PPSA99008`.
6. Kernel pointers used while locating the process are validated and the all-process walk is
   bounded.
7. Before modification, the original credential and filesystem state is captured.
8. The application performs the same-UID credential-clone handshake first. The helper refuses to
   write if the credential pointer did not change or if the cloned state differs from the original.
9. Elevation writes are followed by a full read-back. Success is returned only if the resulting
   state exactly matches the requested state.
10. If application of the elevated state fails, the helper attempts to write and verify the
    original state before returning an error.
11. The helper handles one request and exits. No persistent privilege service is installed by
    Encore.
12. The packaged ELF is validated before release so malformed/trailing data cannot overlap the
    socket protocol that follows the ELF stream.

## Important limitation

The word "filesystem" describes Encore's requested capability, not a kernel-enforced least-
privilege sandbox after success.

To escape the PS5 application sandbox, the helper still applies broad process credentials,
authority/capabilities and root/jail vnode changes. Therefore these checks primarily reduce:

- accidental modification of the wrong process;
- partial credential writes;
- silent elevation failure;
- protocol misuse;
- persistent-service attack surface.

They do **not** make the elevated application harmless if the application, jailbreak environment or
local ELF loader is compromised.

## Runtime use

`main.cpp` records the elevation result in the boot trace and migrates existing sandbox data only
after successful filesystem access. Game-file root selection also rejects `/` so the launcher
cannot be pointed at the entire console root by accident.
