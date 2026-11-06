import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QTableWidget

from main import MainWindow
from results import compare_results, parse_results


class ResultsTests(unittest.TestCase):
    def test_export_format(self):
        for algorithm, length in (("MD5", 32), ("SHA1", 40), ("SHA512", 128)):
            with self.subTest(algorithm=algorithm):
                self.assertEqual(parse_results(f"{'A' * length}  nested/a file ü \r\n\n"),
                                 (algorithm, [("nested/a file ü ", "a" * length)]))

    def test_invalid_results(self):
        for text in ("", "\n", "invalid", "z" * 32 + "  file", "a" * 32 + "  ",
                     "a" * 32 + "  one\n" + "b" * 40 + "  two"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_results(text)

    def test_comparison_statuses(self):
        current = [("same", "AA"), ("changed", "bb"), ("new", "cc"),
                   ("error", ""), ("duplicate", "aa"), ("duplicate", "bb")]
        saved = [("same", "aa"), ("changed", "cc"), ("gone", "dd"),
                 ("error", "aa"), ("duplicate", "aa")]
        self.assertEqual({row[0]: row[3] for row in compare_results(current, saved)},
                         {"same": "Match", "changed": "Different", "new": "Current only",
                          "error": "Not calculated", "duplicate": "Ambiguous filename",
                          "gone": "Saved only"})
        self.assertEqual(compare_results([], [("dup", "aa"), ("dup", "aa")])[0][3],
                         "Ambiguous filename")

    def test_load_compare_preserves_current_results(self):
        self.app = QApplication.instance() or QApplication([])
        window = MainWindow(algorithm="md5")
        window.language_code = "en"
        self.addCleanup(window.close)
        window.add_result("/some/file", "a" * 32, "OK")
        before = window.results_text()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.txt"
            path.write_text(before + "\n", encoding="utf-8-sig")
            with patch("main.QFileDialog.getOpenFileName", return_value=(str(path), "")):
                def inspect(dialog):
                    table = dialog.findChild(QTableWidget)
                    self.assertEqual(table.rowCount(), 1)
                    self.assertEqual(table.item(0, 3).text(), "Match")
                with patch("main.QDialog.exec", new=inspect):
                    window.load_and_compare()
                for content in ("invalid", "b" * 40 + "  file", ""):
                    path.write_text(content, encoding="utf-8")
                    with patch("main.QMessageBox.warning") as warning:
                        window.load_and_compare()
                        warning.assert_called_once()
                self.assertEqual(window.results_text(), before)
            with patch("main.QFileDialog.getOpenFileName", return_value=("", "")):
                window.load_and_compare()
            self.assertEqual(window.results_text(), before)
        window.reset_results()
        self.assertFalse(window.compare.isEnabled())


if __name__ == "__main__":
    unittest.main()
