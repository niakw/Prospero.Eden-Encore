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

Encore has two storage modes:

- **External-storage mode (default):** persistent data lives under `/data/prosperoeden` and Encore
  can use custom/USB game-file folders through the hardened one-shot filesystem helper.
- **Self-contained mode (optional):** Encore never requests filesystem elevation. Keys, firmware,
  games, updates and mods stay under the app's own `assets/` tree; mutable data stays in the
  title-local `/download0` sandbox.

Updating the application does not require deleting either data area.

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

On the normal first Encore startup, that legacy folder can be migrated safely toward
`/data/prosperoeden` when it is still the active game-files location. Existing custom game-files
folders are left untouched, destination conflicts are never overwritten, and a stale setting that
points to an already-removed legacy `assets` folder is repaired to `/data/prosperoeden`.

For an existing ProsperoEden installation, **do this normal first launch before enabling
self-contained mode**. That preserves the old migration path.

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

## Optional self-contained mode — no filesystem elevation

This mode is for users who want the simplest fixed folder layout and do not need a custom/USB
game-files path.

Before launching Encore, keep your own files under the installed title:

```text
/data/homebrew/PPSA99008/assets/keys/prod.keys
/data/homebrew/PPSA99008/assets/firmware/*.nca
/data/homebrew/PPSA99008/assets/roms/
/data/homebrew/PPSA99008/assets/updates/
/data/homebrew/PPSA99008/assets/mods/
/data/homebrew/PPSA99008/assets/save-import/
/data/homebrew/PPSA99008/assets/ryujinx/
```

Then create an empty marker file:

```text
/data/homebrew/PPSA99008/self-contained.txt
```

On the next start, Encore sees that marker through `/app0` before any filesystem request and
**does not contact the elevation helper at all**.

In this mode:

- the game-files root is fixed to `/app0/assets`;
- Settings cannot switch it to another folder;
- keys, firmware, games, updates and mods are read from the app folder;
- settings, saves, logs, caches, save backups and exports are written to `/download0`;
- the RADV/OpenGL shader caches stay in writable sandbox storage;
- if a required key/firmware file is missing, Encore reports setup incomplete instead of falling
  back to elevation.

### Updating a self-contained install

**Do not delete the existing `PPSA99008` folder first.**

Copy the new release files over the existing app folder so your user-created `assets/` tree and
`self-contained.txt` remain in place. The official release ZIP does not contain your keys,
firmware, games or saves.

If you intentionally remove/re-register the title, remember that `/download0` is title-local
sandbox data. Keep your own backups of important saves before destructive title-management work.

To return to external-storage mode, remove `self-contained.txt` and restart Encore.

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

On startup:

- with `self-contained.txt`, Encore stays entirely in its app/sandbox paths and does not request
  filesystem elevation;
- without the marker, Encore uses the external-storage path and its hardened one-shot request.

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

- by itself select self-contained/no-elevation mode;
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
| Can use self-contained no-elevation mode | **Yes** | Official image: No |

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

For external-storage mode:

1. Keep `/data/prosperoeden`.
2. Replace/update the application folder without deleting the persistent data directory.

For self-contained mode:

1. **Do not delete the old `PPSA99008` folder first.**
2. Copy the new release files over it.
3. Preserve your `assets/` tree and `self-contained.txt`.

### FFPFSC installation

Replace the old Encore `.ffpfsc` image with the new release image, then remount/rescan it through
the same ShadowMountPlus workflow you normally use.

Do not delete `/data/prosperoeden` unless you intentionally want to remove Encore's persistent
configuration/data.

---

## User data

In external-storage mode, Encore keeps mutable application data under:

```text
/data/prosperoeden
```

In self-contained mode, mutable application data uses the title's writable `/download0` sandbox
while user-supplied game files remain under `PPSA99008/assets`.

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
