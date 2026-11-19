"""Verify the renderer snapshot against asset-provenance.json.

    python tools/verify_snapshot.py            # check the copies
    python tools/verify_snapshot.py --baseline # also re-check the source

`model/` and `vendor/` are excluded from Git: 20 MB of binary assets and a
third-party library do not belong in this repository. `asset-provenance.json`
is tracked instead, so this is how the snapshot is shown to be the bytes it
claims to be - and how it can be rebuilt from the baseline on another machine.

It checks the record as a closure, not only as a list: every file under the
untracked directories (`model/`, `vendor/`) must be in the record. Those
directories are invisible to Git and the bench page maps `three/addons/` onto
`vendor/` wholesale, so an unlisted file there would be loadable, unseen and
unverified (R05-F11).

Exits non-zero on any mismatch or unexpected file, so it can gate a release
check.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: Directories that are excluded from Git and so are covered only by this tool.
UNTRACKED_DIRS = ("model", "vendor")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unexpected_files(root: Path, assets: list[dict]) -> list[str]:
    """Files under the untracked snapshot directories that no record lists."""
    listed = {a["path"].replace("\\", "/") for a in assets}
    extra = []
    for name in UNTRACKED_DIRS:
        base = root / name
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                if rel not in listed:
                    extra.append(rel)
    return extra


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", action="store_true",
                    help="also verify the recorded source files still match, "
                         "which detects the baseline having moved under us")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    manifest_path = ROOT / "asset-provenance.json"
    if not manifest_path.exists():
        print(f"FAIL: {manifest_path} not found", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets = manifest["assets"]

    missing, changed, baseline_changed, ok = [], [], [], 0
    for asset in assets:
        path = ROOT / asset["path"]
        if not path.exists():
            missing.append(asset["path"])
            continue
        if sha256(path) != asset["sha256"]:
            changed.append(asset["path"])
            continue
        ok += 1
        if args.baseline:
            source = (ROOT / asset["source"]).resolve()
            if not source.exists():
                baseline_changed.append(f"{asset['source']} (missing)")
            elif sha256(source) != asset["sha256"]:
                baseline_changed.append(f"{asset['source']} (differs)")

    unexpected = unexpected_files(ROOT, assets)
    total_bytes = sum(a["bytes"] for a in assets)
    if not args.quiet:
        print(f"snapshot version {manifest['snapshot_version']}, "
              f"created {manifest['created']}")
        print(f"  {ok}/{len(assets)} assets match "
              f"({total_bytes / 1e6:.1f} MB)")
        tracked = sum(1 for a in assets if a["tracked_in_git"])
        print(f"  {tracked} tracked in Git, {len(assets) - tracked} "
              f"excluded by .gitignore and verified by hash only")
    for label, items in (("missing", missing), ("changed", changed),
                         ("unexpected", unexpected),
                         ("baseline drifted", baseline_changed)):
        for item in items:
            print(f"  {label.upper()}: {item}")

    if missing or changed or unexpected:
        print("FAIL: the snapshot does not match its provenance record",
              file=sys.stderr)
        return 1
    if baseline_changed:
        # Not a failure of this snapshot: it is intact. But the baseline it was
        # taken from has moved, so the two are no longer the same bytes and any
        # claim that they are needs re-checking.
        print("WARN: snapshot intact, but the baseline source has changed "
              "since it was taken", file=sys.stderr)
        return 0
    if not args.quiet:
        print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
