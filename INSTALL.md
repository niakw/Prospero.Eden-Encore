# Installing Prospero.Eden Encore

Prospero.Eden Encore provides two release formats. They contain the **same application** and target
the same title ID, `PPSA99008`.

For most users, the **ZIP installation is the recommended method**.

## Before you start

Encore's primary validated target is:

- **PS5 firmware 13.60**
- a working PS5 homebrew/jailbreak environment
- enough writable storage for the application and emulator data

Encore does **not** provide or install console keys, firmware, games, FPKG entitlement support or
kstuff.

Your persistent Encore data is stored under:

```text
/data/prosperoeden
```

Updating the application does not require deleting that directory.

---

## Upgrading from ProsperoEden

Encore deliberately keeps the same title ID (`PPSA99008`) and the same persistent data root:

```text
/data/prosperoeden
```

So ProsperoEden 1.000.020–1.000.040 settings, saves, covers and user data already stored there are
reused directly.

**Do not delete `/data/prosperoeden`.**

For the application itself, the safest upgrade is:

1. Fully close ProsperoEden.
2. **Do not delete the old `PPSA99008` folder first.**
3. Copy/extract Encore's new `PPSA99008` folder over the existing application folder.
4. Launch Encore once.
5. Only after that first successful launch should you remove obsolete duplicate installation
   sources.

Why this matters: very old ProsperoEden layouts could still keep game files under:

```text
/data/homebrew/PPSA99008/assets
```

On first elevated Encore startup, that legacy folder is migrated safely toward
`/data/prosperoeden` when it is still the active game-files location. Existing custom game-files
folders are left untouched, destination conflicts are never overwritten, and a stale setting that
points to an already-removed legacy `assets` folder is repaired to `/data/prosperoeden`.

If the old application folder was physically deleted **before** migration, files that existed only
inside its `assets/` directory cannot be recreated by Encore. Persistent data that was already
under `/data/prosperoeden` is unaffected.

### Switching an existing install to FFPFSC

Migrate/launch the ordinary folder installation first, then switch to FFPFSC if desired.

Do not leave both a `PPSA99008` folder and a `.ffpfsc` image with the same title ID in active
ShadowMountPlus scan locations. The loader may keep or prefer the previously registered source.

If ShadowMountPlus reports **`TitleDir bridge unavailable`**, that failure is in the
ShadowMountPlus/title-registration path, before Encore itself is running. It does not mean Encore's
filesystem elevation failed. Use the ZIP/folder installation path to get Encore running and migrated
first, then troubleshoot the ShadowMountPlus environment separately.

---

## Method 1 — ZIP installation (recommended)

Use this method unless you specifically use ShadowMountPlus.

### 1. Download

From the GitHub Release, download:

```text
Prospero.Eden-Encore-v*.zip
```

Optionally verify it with the matching entry in `SHA256SUMS`.

### 2. Extract the archive

The archive contains a folder named:

```text
PPSA99008
```

### 3. Copy it to the PS5

Copy the complete folder to:

```text
/data/homebrew/PPSA99008
```

The resulting layout should include at least:

```text
/data/homebrew/PPSA99008/eboot.bin
/data/homebrew/PPSA99008/sce_sys/param.json
/data/homebrew/PPSA99008/ui/
```

Do not copy only `eboot.bin`; keep the whole title folder together.

### 4. Launch Encore

Start the application through your normal PS5 homebrew launcher/runtime.

On startup, Encore attempts its one-shot filesystem-access request. If that request is unavailable,
Encore falls back to its sandbox paths instead of reporting a false success.

---

## Method 2 — FFPFSC image with ShadowMountPlus

Use this method only when your environment supports **ShadowMountPlus / FFPFSC images**.

Download:

```text
Prospero.Eden-Encore-v*.ffpfsc
```

The FFPFSC image contains the same `PPSA99008` title as the ZIP, packed into a verified compressed
PFS image.

Depending on your ShadowMountPlus/etaHEN setup, the image can be placed in a supported location such
as:

```text
/data/homebrew
/data/etaHEN/games
```

or in the corresponding supported homebrew location on USB / extended storage.

ShadowMountPlus then mounts the image so the PS5 sees the title contents without you manually
managing the full `PPSA99008` directory.

### Why use FFPFSC?

FFPFSC is useful as an **alternative deployment/mount path**:

- one file instead of a directory tree;
- avoids partial/incomplete folder copies;
- preserves the expected internal title layout;
- the image is verified when it is built;
- can be convenient on USB or setups already using ShadowMountPlus;
- gives users another path when ordinary folder deployment is inconvenient or unreliable.

It does **not**:

- bypass Encore's filesystem elevation;
- repair PS5 FPKG entitlement/PPR;
- replace kstuff;
- make an unsupported firmware compatible;
- contain a different emulator build.

If ShadowMountPlus itself cannot mount the image, use the ZIP method.

---

## ZIP vs FFPFSC

| | ZIP | FFPFSC |
| --- | --- | --- |
| Recommended for most users | **Yes** | No |
| Application contents | Same | Same |
| Manual title folder | Yes | No |
| Requires ShadowMountPlus | No | **Yes** |
| Convenient as one file | No | **Yes** |
| Solves FPKG/kstuff problems | No | No |
| Changes Encore elevation | No | No |

---

## Verifying the download

Each Release includes:

```text
SHA256SUMS
```

It contains the SHA-256 digest of the ZIP and FFPFSC image.

On macOS or Linux:

```bash
shasum -a 256 Prospero.Eden-Encore-v*.zip
shasum -a 256 Prospero.Eden-Encore-v*.ffpfsc
```

Compare the result with `SHA256SUMS`.

---

## Updating Encore

### ZIP installation

1. Keep `/data/prosperoeden`.
2. Replace the application folder:

```text
/data/homebrew/PPSA99008
```

with the new release folder.

### FFPFSC installation

Replace the old Encore `.ffpfsc` image with the new release image, then remount/rescan it through
the same ShadowMountPlus workflow you normally use.

Do not delete `/data/prosperoeden` unless you intentionally want to remove Encore's persistent
configuration/data.

---

## User data

Encore keeps application data separately from the release files:

```text
/data/prosperoeden
```

That area may contain configuration, covers, logs, caches and emulator data created by Encore.

Game files, keys and firmware are not distributed by this project.

---

## If Encore does not start

Try these checks in order:

1. Confirm you are using the complete official release, not a partial folder.
2. Verify the ZIP/FFPFSC SHA-256 checksum.
3. For ZIP installs, confirm `eboot.bin` and `sce_sys/param.json` are under
   `/data/homebrew/PPSA99008`.
4. For FFPFSC, confirm ShadowMountPlus actually mounted the image.
5. Confirm your PS5 homebrew/jailbreak runtime is active.
6. If the launcher opens but a game fails, use **Safe Launch**.
7. Check Encore's **Diagnostics** screen and logs.
8. Remember that PS5 FPKG entitlement/PPR failures are outside Encore and are not fixed by changing
   between ZIP and FFPFSC.

For project support, see [SUPPORT.md](SUPPORT.md).
For security-sensitive problems, see [SECURITY.md](SECURITY.md).
