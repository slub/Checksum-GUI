import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QEventLoop, QLocale, QTimer
from PyQt6.QtWidgets import QApplication

import config
from main import MainWindow


class ConfigAndAutoSaveTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        patcher = patch("config.CONFIG_PATH", self.root / "config.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        locale = patch("main.QLocale.system", return_value=QLocale("en_US"))
        locale.start()
        self.addCleanup(locale.stop)

    def run_calculation(self, window):
        loop = QEventLoop()
        window.start()
        window.worker.finished.connect(loop.quit)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        self.assertIsNone(window.worker, "Calculation did not complete")

    def wait_for_preview(self, window):
        loop = QEventLoop()
        if window.worker is not None:
            window.worker.finished.connect(loop.quit)
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
        self.assertIsNone(window.worker)

    def test_defaults_and_invalid_config(self):
        self.assertEqual(config.load_config(), {"algorithm": "sha512", "recursive": True, "uppercase": True, "auto_save": False, "auto_save_per_directory": False,
                                                "auto_save_name": "checksums.sha512"})
        config.CONFIG_PATH.write_text('{"algorithm": "crc", "auto_save": "yes", "auto_save_name": 3}')
        self.assertEqual(config.load_config()["algorithm"], "sha512")
        config.CONFIG_PATH.write_text("[1]")
        self.assertFalse(config.load_config()["auto_save"])

    def test_settings_persist_and_name_follows_algorithm(self):
        window = MainWindow()
        self.assertEqual(window.auto_save_name.text(), "checksums.sha512")
        self.assertFalse(window.auto_save_name.isEnabled())
        window.algorithm.setCurrentText("MD5")
        self.assertEqual(window.auto_save_name.text(), "checksums.md5")
        window.auto_save.setChecked(True)
        self.assertTrue(window.auto_save_name.isEnabled())
        window.close()
        stored = json.loads(config.CONFIG_PATH.read_text())
        self.assertIn("window_size", stored)
        self.assertIn("column_widths", stored)
        for key in ("window_size", "column_widths", "window_maximized"):
            stored.pop(key)
        self.assertEqual(stored, {"algorithm": "md5", "recursive": True, "uppercase": True, "auto_save": True, "auto_save_per_directory": False, "auto_save_name": "checksums.md5"})
        self.assertNotIn(b"\r\n", config.CONFIG_PATH.read_bytes())

        window = MainWindow()
        self.assertEqual(window.algorithm.currentText(), "MD5")
        self.assertTrue(window.auto_save.isChecked())
        window.auto_save_name.setText("custom.txt")
        window.algorithm.setCurrentText("SHA1")
        self.assertEqual(window.auto_save_name.text(), "custom.txt")
        window.close()
        self.assertEqual(config.load_config()["auto_save_name"], "custom.txt")

        # A command line algorithm is used without being stored.
        window = MainWindow(algorithm="sha512")
        self.assertEqual(window.algorithm.currentText(), "SHA512")
        window.close()
        self.assertEqual(config.load_config()["algorithm"], "sha1")

    def test_auto_save_files_and_folder(self):
        folder = self.root / "data"
        (folder / "nested").mkdir(parents=True)
        (folder / "nested" / "b").write_bytes(b"abc")
        (folder / "a").write_bytes(b"def")
        window = MainWindow(algorithm="md5")
        window.auto_save.setChecked(True)
        window.files = [folder / "a"]
        self.run_calculation(window)
        target = folder / "checksums.md5"
        expected = hashlib.md5(b"def").hexdigest().upper() + "  a\n"
        self.assertEqual(target.read_bytes(), expected.encode())
        self.assertIn("Checksums saved to", window.status.text())

        # The previous checksum file in the folder is not included.
        window.files = []
        window.folder = folder
        window.reset_results()
        self.wait_for_preview(window)
        self.assertEqual(window.table.rowCount(), 2)
        self.run_calculation(window)
        self.assertEqual(target.read_text(), (
            hashlib.md5(b"def").hexdigest().upper() + "  a\n"
            + hashlib.md5(b"abc").hexdigest().upper() + "  nested/b\n"
        ))
        self.assertNotIn(b"\r", target.read_bytes())

        # Enabling auto-save after the folder was listed also excludes the file.
        window.auto_save.setChecked(False)
        window.reset_results()
        self.wait_for_preview(window)
        self.assertEqual(window.table.rowCount(), 3)
        window.auto_save.setChecked(True)
        self.run_calculation(window)
        self.assertEqual(window.table.rowCount(), 2)
        self.assertEqual(len(target.read_text().splitlines()), 2)
        window.close()

    def test_checksum_case_toggle(self):
        window = MainWindow(algorithm="md5")
        self.addCleanup(window.close)
        window.add_result("/some/file", "Ab12" * 8, "OK")
        window.uppercase.setChecked(False)
        self.assertEqual(window.results_text(), "ab12" * 8 + "  file")
        self.assertEqual(window.table.item(0, 1).toolTip(), "ab12" * 8)
        window.table.selectRow(0)
        window.copy_selected_checksums()
        self.assertEqual(self.app.clipboard().text(), "ab12" * 8)
        window.add_result("/some/next", "CD34" * 8, "OK")
        self.assertEqual(window.table.item(1, 1).text(), "cd34" * 8)
        restored = MainWindow()
        self.addCleanup(restored.close)
        self.assertFalse(restored.uppercase.isChecked())
        window.uppercase.setChecked(True)
        self.assertEqual(window.table.item(0, 1).text(), "AB12" * 8)
        self.assertEqual(window.table.item(1, 1).text(), "CD34" * 8)

    def test_per_directory_auto_save(self):
        folder = self.root / "data"
        nested = folder / "nested"
        nested.mkdir(parents=True)
        (folder / "a").write_bytes(b"abc")
        (nested / "b").write_bytes(b"def")
        window = MainWindow(algorithm="md5")
        self.addCleanup(window.close)
        window.folder = folder
        window.auto_save.setChecked(True)
        window.auto_save_per_directory.setChecked(True)
        window.uppercase.setChecked(False)
        self.run_calculation(window)
        for directory, filename, content in ((folder, "a", b"abc"), (nested, "b", b"def")):
            self.assertEqual((directory / "checksums.md5").read_text(),
                             hashlib.md5(content).hexdigest() + "  " + filename + "\n")
        window.reset_results()
        self.wait_for_preview(window)
        self.assertEqual(window.table.rowCount(), 2)
        self.run_calculation(window)
        self.assertEqual(window.table.rowCount(), 2)

        # Explicit file selection across directories also excludes generated files.
        window.folder = None
        window.files = [folder / "a", nested / "b", nested / "checksums.md5"]
        window.reset_results()
        self.run_calculation(window)
        self.assertEqual(window.table.rowCount(), 2)
        self.assertTrue(config.load_config()["auto_save_per_directory"])
        restored = MainWindow()
        self.addCleanup(restored.close)
        self.assertTrue(restored.auto_save_per_directory.isChecked())

    def test_window_and_column_sizes_persist(self):
        window = MainWindow()
        window.resize(1400, 800)
        window.table.setColumnWidth(0, 230)
        window.table.setColumnWidth(1, 750)
        window.close()
        stored = config.load_config()
        self.assertEqual(stored["window_size"], [1400, 800])
        self.assertEqual(stored["column_widths"][:2], [230, 750])
        restored = MainWindow()
        self.addCleanup(restored.close)
        self.assertEqual([restored.width(), restored.height()], [1400, 800])
        self.assertEqual([restored.table.columnWidth(i) for i in range(2)], [230, 750])
        restored.uppercase.setChecked(False)
        self.assertEqual(config.load_config()["column_widths"], stored["column_widths"])

    def test_invalid_window_sizes_are_ignored(self):
        config.CONFIG_PATH.write_text(json.dumps({
            "window_size": [-1, 700], "column_widths": [100, "wide", 100],
            "window_maximized": "yes",
        }))
        settings = config.load_config()
        self.assertNotIn("window_size", settings)
        self.assertNotIn("column_widths", settings)
        self.assertNotIn("window_maximized", settings)

    def test_recursive_option(self):
        folder = self.root / "data"
        (folder / "nested").mkdir(parents=True)
        (folder / "nested" / "b").write_bytes(b"abc")
        (folder / "a").write_bytes(b"def")
        window = MainWindow()
        self.assertTrue(window.recursive.isChecked())
        window.folder = folder
        window.reset_results()
        self.wait_for_preview(window)
        self.assertEqual(window.table.rowCount(), 2)
        window.recursive.setChecked(False)
        self.wait_for_preview(window)
        self.assertEqual(window.table.rowCount(), 1)
        self.assertIn("without subfolders", window.selection.text())
        self.run_calculation(window)
        self.assertEqual(window.results_text(), hashlib.sha512(b"def").hexdigest().upper() + "  a")
        window.close()
        self.assertFalse(config.load_config()["recursive"])
        window = MainWindow()
        self.assertFalse(window.recursive.isChecked())
        window.close()

    def test_no_auto_save_when_disabled_or_cancelled(self):
        (self.root / "a").write_bytes(b"abc")
        window = MainWindow(algorithm="sha1")
        window.files = [self.root / "a"]
        self.run_calculation(window)
        self.assertFalse((self.root / "checksums.sha1").exists())
        window.auto_save.setChecked(True)
        window.add_result(str(self.root / "a"), "A" * 40, "OK")
        window.set_status("Cancelled: {completed} file(s) calculated, {errors} error(s).",
                          dict(completed=1, errors=0))
        window.auto_save_results()
        self.assertFalse((self.root / "checksums.sha1").exists())
        window.close()


if __name__ == "__main__":
    unittest.main()
