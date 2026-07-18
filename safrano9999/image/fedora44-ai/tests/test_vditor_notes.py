import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE = Path(__file__).parents[1] / "services" / "vditor-notes" / "app.py"
SPEC = importlib.util.spec_from_file_location("vditor_notes", MODULE)
APP = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.storage = APP.Storage(Path(self.temporary.name))

    def tearDown(self):
        self.temporary.cleanup()

    def test_markdown_crud_and_tree(self):
        folder = self.storage.create("notes", "directory")
        document = self.storage.create("notes/today", "file")
        document.write_text("# Today", encoding="utf-8")
        self.assertEqual(folder.name, "notes")
        self.assertEqual(document.name, "today.md")
        self.assertEqual(self.storage.tree()[0]["children"][0]["path"], "notes/today.md")
        self.storage.delete("notes/today.md")
        self.assertFalse(document.exists())

    def test_markdown_extension_is_appended(self):
        document = self.storage.create("release.notes", "file")
        self.assertEqual(document.name, "release.notes.md")

    def test_paths_cannot_leave_workspace(self):
        with self.assertRaises(ValueError):
            self.storage.resolve("../outside")
        with self.assertRaises(ValueError):
            self.storage.resolve("/")

    def test_root_cannot_be_deleted(self):
        with self.assertRaises(ValueError):
            self.storage.delete("")


if __name__ == "__main__":
    unittest.main()
