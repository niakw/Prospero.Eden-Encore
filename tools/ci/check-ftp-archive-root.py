#!/usr/bin/env python3
"""Validate installable Eden Encore ZIP member roots without unpacking them.

The canonical distribution ZIP additionally carries legal/readme files at its
root; the dedicated FTP ZIP MUST carry only PPSA99008/ runtime paths.
"""
import argparse
import io
import json
import pathlib
import zipfile

TITLE = "PPSA99008"
REQUIRED = {f"{TITLE}/eboot.bin", f"{TITLE}/sce_sys/param.json"}


def inspect(blob: bytes, ftp_only: bool) -> int:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = z.namelist()
        assert len(names) == len(set(names)), "Duplicate archive entries"
        files = {name for name in names if not name.endswith("/")}
        assert REQUIRED <= files, f"Missing {REQUIRED-files}"
        assert "eboot.bin" not in files, "Flattened title directory"
        assert f"{TITLE}/{TITLE}/eboot.bin" not in files, "Nested title directory"
        assert all(not name.startswith("/") and "\\" not in name and
                   not {"", ".", ".."} & set(pathlib.PurePosixPath(name).parts)
                   for name in names), "Unsafe archive member path"
        if ftp_only:
            assert all(name.startswith(f"{TITLE}/") for name in names), "FTP archive has extra root content"
            assert not any(name.lower().endswith(".zip") for name in names), "Nested zip prohibited"
        param = json.loads(z.read(f"{TITLE}/sce_sys/param.json"))
        assert param["titleId"] == TITLE, "PS5 metadata title differs from folder"
        assert z.getinfo(f"{TITLE}/eboot.bin").file_size > 0, "Missing binary payload"
        return len(files)


def self_test() -> None:
    def build(prefix: str, extra: bool = False):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as z:
            z.writestr(prefix+"eboot.bin", b"\x7fELF")
            z.writestr(prefix+"sce_sys/param.json", '{"titleId":"PPSA99008"}')
            if extra:
                z.writestr("README.md", "full release docs")
        return output.getvalue()
    assert inspect(build("PPSA99008/"), True) == 2
    assert inspect(build("PPSA99008/", True), False) == 3
    for bad in ["", "PPSA99008/PPSA99008/", "WrongFolder/"]:
        try:
            inspect(build(bad), True)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"Incorrect ZIP root accepted: {bad!r}")
    try:
        inspect(build("PPSA99008/", True), True)
    except AssertionError:
        pass
    else:
        raise AssertionError("Unrelated root-level file in FTP ZIP was accepted")
    print("ENCORE_PPSA99008_ZIP_LAYOUT_HOST_PASS flat=reject nested=reject extra=reject")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", nargs="?", type=pathlib.Path)
    parser.add_argument("--self-test", action="store_true")
    opts = parser.parse_args()
    if opts.self_test:
        self_test()
        return
    if opts.dist is None:
        parser.error("provide dist folder or --self-test")
    ftp = sorted(opts.dist.glob("Prospero.Eden-Encore-*-FTP.zip"))
    full = sorted(path for path in opts.dist.glob("Prospero.Eden-Encore-*.zip")
                  if not path.name.endswith("-FTP.zip"))
    if len(ftp) != 1 or len(full) != 1:
        raise SystemExit(f"Expected one FTP and one full ZIP: {ftp}, {full}")
    print(f"ENCORE_FTP_ZIP_ROOT_OK PPSA99008/ files={inspect(ftp[0].read_bytes(), True)}")
    print(f"ENCORE_FULL_ZIP_ROOT_OK PPSA99008/ files={inspect(full[0].read_bytes(), False)}")


if __name__ == "__main__":
    main()
