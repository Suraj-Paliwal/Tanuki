"""Tests for tools/verify_snapshot.py's closure check (R05-F11).

`model/` and `vendor/` are excluded from Git, so the provenance record is the
only thing that says what bytes they hold. These check that a file the record
does not list is reported, on a temporary tree rather than the real snapshot.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from verify_snapshot import unexpected_files  # noqa: E402


class ClosureTest(unittest.TestCase):
    def _tree(self, root: Path, files: list[str]) -> None:
        for rel in files:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")

    def test_a_fully_listed_tree_has_nothing_unexpected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root, ["model/a.gltf", "vendor/three/addons/b.js"])
            assets = [{"path": "model/a.gltf"},
                      {"path": "vendor/three/addons/b.js"}]
            self.assertEqual(unexpected_files(root, assets), [])

    def test_an_unlisted_file_under_vendor_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root, ["model/a.gltf", "vendor/three/addons/stray.js"])
            assets = [{"path": "model/a.gltf"}]
            self.assertEqual(unexpected_files(root, assets),
                             ["vendor/three/addons/stray.js"])

    def test_tracked_directories_are_left_to_git(self):
        """src/ is tracked, so Git already shows an extra file there."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root, ["src/extra.js"])
            self.assertEqual(unexpected_files(root, []), [])


if __name__ == "__main__":
    unittest.main()
