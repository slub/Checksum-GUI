import hashlib
import tempfile
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from PyQt6.QtCore import QEventLoop, QTimer, QLocale, QMimeData, QPoint, QPointF, Qt, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import QApplication

from checksums import Cancelled, checksum_file
from main import MainWindow, VERSION, parse_arguments
from taskbar import TaskbarProgress


class ChecksumTests(unittest.TestCase):
    def test_table_file_and_folder_drops(self):
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first file", root / "second"
            first.write_bytes(b"abc")
            second.write_bytes(b"def")

            def drop(urls, accepted):
                mime = QMimeData()
                mime.setUrls(urls)
                enter = QDragEnterEvent(QPoint(5, 5), Qt.DropAction.CopyAction,
                                        mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
                QApplication.sendEvent(window.table.viewport(), enter)
                self.assertEqual(enter.isAccepted(), accepted)
                event = QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction,
                                   mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
                QApplication.sendEvent(window.table.viewport(), event)
                self.assertEqual(event.isAccepted(), accepted)

            window.add_result(str(first), "old digest", "OK")
            drop([QUrl.fromLocalFile(str(p)) for p in (first, second, first)], True)
            self.assertEqual(window.files, [first, second])
            self.assertIsNone(window.folder)
            self.assertEqual(window.table.rowCount(), 0)
            self.assertTrue(window.calculate.isEnabled())
            drop([QUrl.fromLocalFile(str(root))], True)
            self.assertEqual(window.folder, root)
            self.assertEqual(window.files, [])
            for urls in (
                [QUrl("https://example.com/file")],
                [QUrl.fromLocalFile(str(root)), QUrl.fromLocalFile(str(first))],
                [QUrl.fromLocalFile(str(root / "missing"))],
            ):
                drop(urls, False)
                self.assertEqual(window.folder, root)
            window.worker = Mock()
            drop([QUrl.fromLocalFile(str(first))], False)
            self.assertEqual(window.folder, root)
            window.worker = None
        window.close()

    def setUp(self):
        notifications = patch("main.DesktopNotifications.show")
        notifications.start()
        self.addCleanup(notifications.stop)

    def test_completion_notification_only_when_unfocused(self):
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        window.language_code = "en"
        window.notifications.show = Mock()
        finished = "Finished: {completed} file(s) calculated, {errors} error(s)."
        cancelled = "Cancelled: {completed} file(s) calculated, {errors} error(s)."
        for active, closing, message, expected in (
            (False, False, finished, True),
            (True, False, finished, False),
            (False, True, finished, False),
            (False, False, cancelled, False),
        ):
            with self.subTest(active=active, closing=closing, message=message):
                window.notifications.show.reset_mock()
                window.worker = Mock()
                window.close_pending = closing
                window.set_status(message, dict(completed=2, errors=1))
                with patch.object(window, "isActiveWindow", return_value=active):
                    window.finished()
                if expected:
                    window.notifications.show.assert_called_once_with(
                        "Checksum Calculator", "Finished: 2 file(s) calculated, 1 error(s)."
                    )
                else:
                    window.notifications.show.assert_not_called()
        window.close_pending = False
        window.close()

    def test_command_line_startup(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "file with spaces"
            path.write_bytes(b"abc")
            for paths in ([str(path), str(path)], [str(root)]):
                with self.subTest(paths=paths):
                    args = parse_arguments(["-a", "MD5", *paths])
                    self.assertEqual(len(args.paths), 1)
                    window = MainWindow(args.paths, args.algorithm)
                    window.show()
                    loop = QEventLoop()
                    # The startup callback is queued before this callback.
                    QTimer.singleShot(0, lambda: window.worker.finished.connect(loop.quit))
                    timer = QTimer()
                    timer.setSingleShot(True)
                    timer.timeout.connect(loop.quit)
                    timer.start(5000)
                    loop.exec()
                    if window.worker is not None:
                        window.stop()
                        window.worker.wait()
                        app.processEvents()
                        self.fail("Automatic calculation did not complete")
                    self.assertEqual(window.table.rowCount(), 1)
                    self.assertEqual(window.table.item(0, 1).text(),
                                     hashlib.md5(b"abc", usedforsecurity=False).hexdigest())
                    window.close()
        window = MainWindow(parse_arguments([]).paths)
        app.processEvents()
        self.assertIsNone(window.worker)
        self.assertFalse(window.calculate.isEnabled())
        window.close()

    def test_command_line_rejects_mixed_folder_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("sys.stderr"), self.assertRaises(SystemExit) as error:
                parse_arguments([directory, "file"])
            self.assertEqual(error.exception.code, 2)

    def test_taskbar_progress_states(self):
        with patch("taskbar.sys.platform", "linux"):
            taskbar = TaskbarProgress(Mock())
        taskbar.update(total=0, active=True)
        self.assertEqual(taskbar.state, 1)
        taskbar.update(3, 10, active=True)
        self.assertEqual((taskbar.state, taskbar.completed, taskbar.total), (2, 3, 10))
        taskbar.update()
        self.assertEqual(taskbar.state, 0)
        taskbar.close()

    def test_system_language(self):
        app = QApplication.instance() or QApplication([])
        for locale, language, title in (
            ("de_DE", "de", "Prüfsummenrechner"),
            ("de_AT", "de", "Prüfsummenrechner"),
            ("en_GB", "en", "Checksum Calculator"),
            ("fr_FR", "en", "Checksum Calculator"),
            ("C", "en", "Checksum Calculator"),
        ):
            with self.subTest(locale=locale), patch("main.QLocale.system", return_value=QLocale(locale)):
                window = MainWindow()
                self.assertEqual(window.language_code, language)
                self.assertEqual(window.windowTitle(), title + " " + VERSION)
                window.close()
                window.deleteLater()
        app.processEvents()

    def test_streamed_content_and_empty_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data"
            for content in (b"", b"abc", b"abcdef" * 400_000):
                path.write_bytes(content)
                self.assertEqual(checksum_file(path), hashlib.sha512(content).hexdigest())
                for algorithm in ("sha1", "md5", "sha512"):
                    with self.subTest(algorithm=algorithm, size=len(content)):
                        self.assertEqual(
                            checksum_file(path, algorithm),
                            hashlib.new(algorithm, content, usedforsecurity=False).hexdigest(),
                        )

    def test_cancellation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data"
            path.write_bytes(b"abc")
            with self.assertRaises(Cancelled):
                checksum_file(path, cancelled=lambda: True)

    @patch("main.QLocale.system", return_value=QLocale("en_US"))
    def test_folder_gui_and_missing_file(self, _system_locale):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "nested" / "data").write_bytes(b"abc")
            window = MainWindow()
            window.taskbar.update = Mock()
            self.assertEqual(window.algorithm.currentText(), "SHA512")
            window.algorithm.setCurrentText("MD5")
            self.assertFalse(window.calculate.isEnabled())
            window.folder = root
            window.files = [root / "missing"]
            loop = QEventLoop()
            window.start()
            window.taskbar.update.assert_called_with(total=0, active=True)
            self.assertFalse(window.algorithm.isEnabled())
            window.worker.finished.connect(loop.quit)
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            timer.start(5000)
            loop.exec()
            if window.worker is not None:
                window.worker.requestInterruption()
                window.worker.wait()
                app.processEvents()
                self.fail("Worker did not complete in time")
            self.assertEqual(window.table.rowCount(), 2)
            window.taskbar.update.assert_any_call(0, 2, active=True)
            window.taskbar.update.assert_any_call(2, 2, active=True)
            window.taskbar.update.assert_called_with()
            self.assertEqual(window.table.item(1, 1).text(), hashlib.md5(b"abc", usedforsecurity=False).hexdigest())
            self.assertIn("1 error(s)", window.status.text())
            self.assertTrue(window.calculate.isEnabled())
            window.copy_results()
            self.assertIn(hashlib.md5(b"abc", usedforsecurity=False).hexdigest(), app.clipboard().text())
            self.assertTrue(window.algorithm.isEnabled())
            self.assertEqual(window.table.horizontalHeaderItem(1).text(), "MD5")
            previous_results = window.results_text()
            window.language_code = "de"
            window.retranslate_ui()
            self.assertEqual(window.windowTitle(), "Prüfsummenrechner " + VERSION)
            self.assertEqual(window.calculate.text(), "Berechnen")
            self.assertEqual(window.table.horizontalHeaderItem(0).text(), "Datei")
            self.assertEqual(window.status.text(), "Fertig: 1 Datei(en) berechnet, 1 Fehler.")
            self.assertEqual(window.results_text(), previous_results)
            window.language_code = "en"
            window.retranslate_ui()
            self.assertIn("1 error(s)", window.status.text())
            window.algorithm.setCurrentText("SHA1")
            self.assertEqual(window.table.rowCount(), 0)
            self.assertEqual(window.calculate.text(), "Calculate")
            self.assertFalse(window.copy.isEnabled())
            window.close()


if __name__ == "__main__":
    unittest.main()
