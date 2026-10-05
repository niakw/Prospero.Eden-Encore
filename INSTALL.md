# Installing Prospero.Eden Encore

Prospero.Eden Encore targets **PS5 firmware 13.60** and keeps one simple storage contract.

The application title is:

```text
PPSA99008
```

The default storage root is:

```text
/data/prosperoeden
```

## Storage layout

Encore always expects the same folder structure under the selected storage root:

```text
<root>/
├── keys/
│   └── prod.keys
├── firmware/
├── roms/
├── updates/
├── mods/
├── save-import/
├── save-export/
└── ryujinx/
```

With the default internal root, that means for example:

```text
/data/prosperoeden/keys/prod.keys
/data/prosperoeden/firmware/
/data/prosperoeden/roms/
/data/prosperoeden/updates/
/data/prosperoeden/mods/
```

Application-managed data also stays under `/data/prosperoeden`:

```text
/data/prosperoeden/config/
/data/prosperoeden/logs/
/data/prosperoeden/covers/
/data/prosperoeden/user/
/data/prosperoeden/cache/
/data/prosperoeden/backup/
```

### External storage

You may choose another **root** in **Settings → Storage**.

Only the root changes. The structure does not.

For example, an external root must still contain:

```text
<external root>/keys/
<external root>/firmware/
<external root>/roms/
<external root>/updates/
<external root>/mods/
<external root>/save-import/
<external root>/save-export/
<external root>/ryujinx/
```

Encore creates the standard subfolders when a valid writable external root is selected.

It does not support separate custom paths for keys, firmware, games, updates or mods.

---

## Upgrading from ProsperoEden

Encore preserves title ID `PPSA99008` and the existing persistent data root used by later
ProsperoEden builds:

```text
/data/prosperoeden
```

So data already stored there is reused directly.

### Recommended upgrade procedure

1. Fully close ProsperoEden.
2. **Do not delete `/data/prosperoeden`.**
3. Prefer copying the Encore `PPSA99008` folder over the existing application folder instead of
   deleting the old app first.
4. Launch Encore once and let migration complete.
5. Confirm your keys, firmware and games are visible before removing obsolete copies.

Very old layouts may still contain user files under:

```text
/data/homebrew/PPSA99008/assets
```

Encore migrates that legacy layout toward `/data/prosperoeden` when it is still the active
ProsperoEden storage location.

Migration is guarded so that:

- symlinked or unexpected source entries are rejected;
- destination conflicts are not overwritten;
- the whole move is preflighted before data is moved;
- moved directories are rolled back if the operation or settings update fails.

If an older configuration already points to a real external storage root, Encore keeps that root
instead of forcing the data back to internal storage.

If the old application folder was deleted before migration, files that existed **only** inside its
legacy `assets/` directory cannot be recreated. Data already under `/data/prosperoeden` is
unaffected.

---

## Method 1 — ZIP installation

This is the recommended installation method.

### 1. Download

Download:

```text
Prospero.Eden-Encore-v*.zip
```

The Release also includes `SHA256SUMS`.

### 2. Extract the title

The archive contains:

```text
PPSA99008/
```

Copy the complete folder to:

```text
/data/homebrew/PPSA99008
```

The installation should include at least:

```text
/data/homebrew/PPSA99008/eboot.bin
/data/homebrew/PPSA99008/sce_sys/param.json
/data/homebrew/PPSA99008/ui/
```

Do not copy only `eboot.bin`.

### 3. Prepare storage

For the default internal layout, place your own files under:

```text
/data/prosperoeden/keys/
/data/prosperoeden/firmware/
/data/prosperoeden/roms/
```

Encore creates the normal folder structure automatically once filesystem access is available.

### 4. Launch Encore

Encore performs its one-shot filesystem-access request during startup, then uses the selected
storage root.

If filesystem access cannot be obtained, Encore remains in its normal PS5 sandbox rather than
pretending access succeeded. External and `/data/prosperoeden` storage will not be treated as
available in that state.

---

## Method 2 — FFPFSC with ShadowMountPlus

The optional `.ffpfsc` contains the same Encore application as the ZIP, packed as a compressed PFS
image for compatible ShadowMountPlus / etaHEN setups.

Download:

```text
Prospero.Eden-Encore-v*.ffpfsc
```

It can be placed in a location supported by your ShadowMountPlus setup, for example a compatible
homebrew/game scan directory on internal or USB storage.

### What FFPFSC changes

FFPFSC changes **how the application itself is mounted**.

It does not change Encore's storage layout:

```text
/data/prosperoeden
```

remains the default storage root unless you select an external root.

FFPFSC does not:

- repair FPKG entitlement/PPR;
- replace kstuff;
- bypass Encore's filesystem-access request;
- change firmware compatibility.

### `TitleDir bridge unavailable`

If ShadowMountPlus reports:

```text
TitleDir bridge unavailable
```

the failure occurs in the ShadowMountPlus/title-registration path **before Encore runs**.

It is not an Encore storage-migration or elevation error.

Use the ZIP/folder installation to validate Encore itself, then troubleshoot the ShadowMountPlus
environment separately.

When migrating an existing ProsperoEden installation, it is safest to complete the first Encore
launch with the ordinary folder installation before switching to FFPFSC.

---

## Verifying the download

Compare the downloaded files with `SHA256SUMS`.

On macOS or Linux:

```bash
shasum -a 256 Prospero.Eden-Encore-v*.zip
shasum -a 256 Prospero.Eden-Encore-v*.ffpfsc
```

---

## Updating Encore

### Application

Replace the old `PPSA99008` application files with the new release.

Do **not** delete:

```text
/data/prosperoeden
```

unless you intentionally want to remove Encore's persistent internal data.

### External storage

If you use an external root, keep that root in place. Encore continues to expect the same standard
subfolders after an update.

### FFPFSC

Replace the old Encore `.ffpfsc` image with the new one and remount/rescan it using the same
ShadowMountPlus workflow.

---

## If Encore reports setup incomplete

Check the selected storage root.

For the default internal root:

```text
/data/prosperoeden/keys/prod.keys
/data/prosperoeden/firmware/*.nca
/data/prosperoeden/roms/
```

The launcher validates that:

- `prod.keys` exists and supplies the required keys;
- the firmware folder contains readable NCA files;
- firmware SystemVersion data is present.

If you selected external storage, check the same folders under that external root.

---

## If Encore does not start

1. Verify the release checksum.
2. Confirm the complete `PPSA99008` folder/image is present.
3. Confirm the PS5 homebrew/jailbreak runtime is active.
4. Check Encore's Diagnostics/logs.
5. Use **Safe Launch** for a title that stopped booting after settings changes.
6. Remember that FPKG/PPR and general kstuff problems are outside Encore.

For support, see [SUPPORT.md](SUPPORT.md).

For security-sensitive reports, see [SECURITY.md](SECURITY.md).
