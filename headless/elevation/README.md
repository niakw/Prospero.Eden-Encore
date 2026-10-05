# Filesystem access (sandbox elevation)

Encore keeps the ProsperoEden 1.000.040 one-shot filesystem helper instead of adopting the newer
Lapy path.

It supports Encore's single storage model:

- default internal root: `/data/prosperoeden`;
- optional external root selected by the user;
- identical folder schema under either root.

The implementation originates from
[ps5-native-app-boilerplate](https://github.com/blackbearreloaded/ps5-native-app-boilerplate)
`examples/sandbox-elevation` at `dd44bbd` (GPL-3.0-or-later).

## Encore target

- Application title ID: `PPSA99008`.
- Primary validated firmware target: **PS5 13.60**.
- Requested capability: `Capability::filesystem`.
- Helper packaged as `/app0/sandbox-elevator.elf`.
- Request made once during single-threaded startup.
- Without a usable local ELF-loader/elevation path, the request fails and Encore remains sandboxed
  rather than treating access as successful.

Other firmware versions are not claimed as validated by Encore until tested on hardware.

## Security properties

This path is intentionally one-shot and narrow at the protocol boundary:

1. The application connects only to the local ELF-loader endpoint at `127.0.0.1:9021`.
2. Connect/send/receive operations use bounded five-second timeouts.
3. The protocol is a fixed 24-byte little-endian structure with magic, version, kind, capability,
   PID and status validation.
4. Only `Capability::filesystem` is accepted. Arbitrary privilege masks, addresses and kernel
   pointers are not supplied by the application.
5. The helper validates the requested PID against the exact title ID `PPSA99008`.
6. Kernel pointers used while locating the process are validated and process traversal is bounded.
7. Original credential/filesystem state is captured before modification.
8. The application performs the same-UID credential-clone handshake first.
9. The helper refuses to write if the credential pointer did not change or the clone differs from
   the captured original state.
10. Elevated state is read back and must exactly match the intended state.
11. A failed apply attempts a full write-back and verification of the original state.
12. The helper handles one request and exits; Encore installs no persistent elevation service.
13. The packaged ELF is structurally validated before release.
14. The application independently checks user/group identity after the helper returns.
15. `rollback_failed`, any failed request that changed identity, or a reported success with an
    unexpected identity terminates the process before privileged filesystem use.
16. Legacy data migration validates the entire source tree before copying/moving and rejects
    symlinks or unexpected file types.
17. Legacy game-file migration is preflighted and rollback-aware; destination conflicts are never
    silently overwritten.

## Runtime use

After successful filesystem access, Encore resolves one storage root.

Internal storage uses:

```text
/data/prosperoeden
```

An external selection changes only that root; it does not create separate configurable paths for
keys, firmware, ROMs, updates or mods.

`main.cpp` records the access result in the boot trace, performs guarded legacy migration, creates
the standard root subfolders where possible, and then starts normal launcher/runtime initialization.

The Storage browser rejects `/` so the console root cannot be selected accidentally.
