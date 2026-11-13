"""Mailbox generation and installation regression checks (no mail client needed)."""

import contextlib
import mailbox
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent
MESSAGE = b"From: sender@example.com\nTo: recipient@example.com\nSubject: Receipt\n\nFrom the team\n"


class MailboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.region = self.base / "region"
        self.region.mkdir()
        self.eml = self.region / "receipt.eml"
        self.eml.write_bytes(MESSAGE)
        self.output = self.base / "exports"

    def build(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "build_region_mbox.py"), str(self.region),
             "--output-dir", str(self.output), *args],
            check=True, capture_output=True, text=True,
        ).stdout

    def test_maildir_preserves_bytes_and_skips_unchanged(self):
        duplicate = self.region / "emails"
        duplicate.mkdir()
        (duplicate / "duplicate.eml").write_bytes(MESSAGE)
        self.build()
        target = self.output / "region"
        files = list((target / "cur").iterdir())
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_bytes(), MESSAGE)
        self.assertTrue((target / "tmp").is_dir())
        mtime = files[0].stat().st_mtime_ns
        self.assertIn("unchanged", self.build())
        self.assertEqual(files[0].stat().st_mtime_ns, mtime)
        self.eml.write_bytes(MESSAGE + b"Updated\n")
        self.assertIn("would_write", self.build("--dry-run"))
        self.assertEqual(files[0].read_bytes(), MESSAGE)
        self.build()
        self.assertEqual(files[0].read_bytes(), self.eml.read_bytes())
        self.eml.unlink()
        self.assertIn("would_remove", self.build("--dry-run"))
        self.assertTrue(target.exists())
        self.build()
        self.assertFalse(target.exists())

    def test_switch_formats_and_force(self):
        self.build()
        self.build("--format", "mbox")
        target = self.output / "region"
        self.assertTrue(target.is_file())
        with contextlib.closing(mailbox.mbox(target, create=False)) as messages:
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]["Subject"], "Receipt")
        self.assertIn("unchanged", self.build("--format", "mbox"))
        self.assertIn("wrote", self.build("--format", "mbox", "--force"))
        self.build()
        self.assertTrue((target / "cur").is_dir())

    def test_installer_copies_maildir_and_backs_up_previous_mailbox(self):
        self.build()
        installer = self.output / "import_mailboxes.py"
        shutil.copyfile(ROOT / "thunderbird/import_mailboxes.py", installer)
        destination = self.base / "Local Folders"
        destination.mkdir()
        (destination / "region").write_bytes(b"previous mailbox")
        (destination / "region.msf").write_bytes(b"previous index")
        command = [sys.executable, str(installer), str(destination)]
        subprocess.run(command, check=True, capture_output=True)
        self.assertEqual((destination / "region/cur/00000000.eml").read_bytes(), MESSAGE)
        backup = next(self.base.glob("bird-backup-*"))
        self.assertEqual((backup / "region").read_bytes(), b"previous mailbox")
        self.assertEqual((backup / "region.msf").read_bytes(), b"previous index")
        subprocess.run(command, check=True, capture_output=True)
        self.assertEqual(len(list((destination / "region/cur").iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
