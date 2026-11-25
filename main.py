#!/usr/bin/env python3

import argparse
import os
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, QTranslator, QLibraryInfo, QLocale
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMainWindow,
    QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QAbstractItemView, QComboBox, QMessageBox, QDialog, QDialogButtonBox, QCheckBox, QLineEdit,
)

from checksums import Cancelled, checksum_file
from translations import LANGUAGES, translate
from taskbar import TaskbarProgress
from notifications import DesktopNotifications
from results import parse_results, compare_results
from config import default_auto_save_name, load_config, save_config


VERSION = "2.1.0"

def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description="Calculate checksums for files or a folder.")
    parser.add_argument("paths", nargs="*", type=Path,
                        help="Files or one folder (subfolders as last chosen in the GUI)")
    parser.add_argument("-a", "--algorithm", type=str.lower,
                        choices=("sha512", "sha1", "md5"), default=None,
                        help="Defaults to the last algorithm used in the GUI")
    args = parser.parse_args(argv)
    args.paths = list(dict.fromkeys(path.absolute() for path in args.paths))
    if any(path.is_dir() for path in args.paths) and len(args.paths) != 1:
        parser.error("Supply either (multiple) files or a single folder.")
    return args

FINISHED_MESSAGE = "Finished: {completed} file(s) calculated, {errors} error(s)."


def write_results(path: Path, text: str):
    # Always LF line endings, also on Windows.
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def detect_language():
    language = QLocale.system().name().split("_")[0]
    return language if language in LANGUAGES else "en"


class ChecksumWorker(QThread):
    discovered = pyqtSignal(int)
    result = pyqtSignal(str, str, str)
    progress = pyqtSignal(int)
    summary = pyqtSignal(str, dict)

    def __init__(self, files: list[Path], folder: Path | None, parent=None, algorithm="sha512", preview_only=False,
                 exclude: Path | None = None, recursive=True):
        super().__init__(parent)
        self.files = files
        self.folder = folder
        self.algorithm = algorithm
        self.preview_only = preview_only
        # The automatically saved checksum file must not checksum itself.
        self.exclude = exclude
        self.recursive = recursive

    def run(self):
        completed = errors = 0
        try:
            files = list(self.files)
            if self.folder is not None:
                def walk_error(error):
                    nonlocal errors
                    errors += 1
                    self.result.emit(str(error.filename), "", str(error))

                for root, directories, names in os.walk(self.folder, onerror=walk_error):
                    if self.isInterruptionRequested():
                        raise Cancelled()
                    if self.recursive:
                        directories.sort()
                    else:
                        directories.clear()
                    for name in sorted(names):
                        path = Path(root) / name
                        # Avoid devices, FIFOs, and symbolic links when scanning folders.
                        if not path.is_symlink() and path.is_file() and path != self.exclude:
                            files.append(path)
            self.discovered.emit(len(files))
            if self.preview_only or self.folder is not None:
                for path in files:
                    if self.isInterruptionRequested():
                        raise Cancelled()
                    self.result.emit(str(path), "", "")
            if self.preview_only:
                self.summary.emit("Ready", {})
                return
            for index, path in enumerate(files, 1):
                if self.isInterruptionRequested():
                    raise Cancelled()
                self.result.emit(str(path), "", "0%")
                try:
                    digest = checksum_file(
                        path, self.algorithm, self.isInterruptionRequested,
                        progress=lambda percent: self.result.emit(str(path), "", f"{percent}%"),
                    )
                    self.result.emit(str(path), digest, "OK")
                    completed += 1
                except OSError as error:
                    errors += 1
                    self.result.emit(str(path), "", str(error))
                except Cancelled:
                    self.result.emit(str(path), "", "Cancelled")
                    raise
                except Exception as error:
                    self.result.emit(str(path), "", str(error))
                    raise
                self.progress.emit(index)
            self.summary.emit(FINISHED_MESSAGE, dict(completed=completed, errors=errors))
        except Cancelled:
            self.summary.emit("Cancelled: {completed} file(s) calculated, {errors} error(s).", dict(completed=completed, errors=errors))
        except Exception as error:
            self.summary.emit("Calculation failed: {error}", dict(error=str(error)))


class FileDropTable(QTableWidget):
    paths_dropped = pyqtSignal(list)

    def __init__(self, window):
        super().__init__(0, 3, window)
        self.window = window
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

    def drop_paths(self, event):
        if self.window.worker is not None:
            return []
        urls = event.mimeData().urls()
        if not urls or any(not url.isLocalFile() for url in urls):
            return []
        paths = list(dict.fromkeys(Path(url.toLocalFile()) for url in urls))
        if len(paths) == 1 and paths[0].is_dir():
            return paths
        return paths if all(path.is_file() for path in paths) else []

    def dragEnterEvent(self, event):
        if self.drop_paths(event) and event.possibleActions() & Qt.DropAction.CopyAction:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        paths = self.drop_paths(event)
        if paths and event.possibleActions() & Qt.DropAction.CopyAction:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.paths_dropped.emit(paths)
        else:
            event.ignore()


class MainWindow(QMainWindow):
    def __init__(self, paths=None, algorithm=None):
        super().__init__()
        config = load_config()
        algorithm = algorithm or config["algorithm"]
        self.settings_loaded = False
        self.taskbar = TaskbarProgress(self)
        QApplication.instance().aboutToQuit.connect(self.taskbar.close)
        self.files: list[Path] = []
        self.folder: Path | None = None
        self.worker: ChecksumWorker | None = None
        self.result_rows: dict[str, int] = {}
        self.preview_files: list[Path] | None = None
        self.close_pending = False
        self.status_message = ("Ready", {})
        self.language_code = detect_language()
        self.qt_translator = QTranslator(self)
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().with_name("icon.ico"))))
        self.notifications = DesktopNotifications(self)
        self.resize(1200, 700)

        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)
        buttons = QHBoxLayout()
        self.select_files = QPushButton("Select files…")
        self.select_folder = QPushButton("Select folder…")
        self.algorithm = QComboBox()
        self.algorithm.addItems(["SHA512", "SHA1", "MD5"])
        self.algorithm.setAccessibleName("Checksum algorithm")
        self.algorithm_label = QLabel("Algorithm:")
        buttons.addWidget(self.algorithm_label)
        buttons.addWidget(self.algorithm)
        self.calculate = QPushButton("Calculate")
        calculate_font = self.calculate.font()
        calculate_font.setBold(True)
        self.calculate.setFont(calculate_font)
        self.copy = QPushButton("Copy results")
        self.save = QPushButton("Save results…")
        self.compare = QPushButton("Load and compare…")
        self.recursive = QCheckBox("Include subfolders")
        self.recursive.setChecked(config["recursive"])
        for button in (self.select_files, self.select_folder, self.recursive, self.calculate):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.auto_save = QCheckBox("Save checksums automatically after completion as")
        self.auto_save.setChecked(config["auto_save"])
        self.auto_save_name = QLineEdit(config["auto_save_name"])
        self.auto_save_name.setEnabled(self.auto_save.isChecked())
        self.selection = QLabel("Select files or a folder to begin, or drag-and-drop files onto the the table or the executable itself.")
        self.selection.setWordWrap(True)
        layout.addWidget(self.selection)
        self.table = FileDropTable(self)
        self.table.paths_dropped.connect(self.select_dropped_paths)
        self.table.setHorizontalHeaderLabels(["File", "SHA512", "Status"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.copy_checksums_action = copy_checksums = QAction("Copy checksums", self.table)
        copy_checksums.setShortcut(QKeySequence.StandardKey.Copy)
        copy_checksums.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        copy_checksums.triggered.connect(self.copy_selected_checksums)
        self.table.addAction(copy_checksums)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 135)
        self.table.setColumnWidth(1, 925)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.status = QLabel("Ready")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        results_buttons = QHBoxLayout()
        results_buttons.addWidget(self.auto_save)
        results_buttons.addWidget(self.auto_save_name, 1)
        results_buttons.addWidget(self.copy)
        results_buttons.addWidget(self.save)
        results_buttons.addWidget(self.compare)
        layout.addLayout(results_buttons)
        self.calculate.setEnabled(False)
        self.copy.setEnabled(False)
        self.save.setEnabled(False)
        self.compare.setEnabled(False)
        self.select_files.clicked.connect(self.choose_files)
        self.select_folder.clicked.connect(self.choose_folder)
        self.calculate.clicked.connect(self.toggle_calculation)
        self.copy.clicked.connect(self.copy_results)
        self.save.clicked.connect(self.save_results)
        self.compare.clicked.connect(self.load_and_compare)
        self.algorithm.currentTextChanged.connect(self.algorithm_changed)
        self.auto_save.toggled.connect(self.auto_save_toggled)
        self.recursive.toggled.connect(self.recursive_toggled)
        self.auto_save_name.textChanged.connect(self.save_settings)
        self.retranslate_ui()
        self.current_algorithm = self.algorithm.currentText()
        self.algorithm.setCurrentText(algorithm.upper())
        # Algorithms passed on the command line apply only to this session.
        self.settings_loaded = True
        if paths:
            if len(paths) == 1 and paths[0].is_dir():
                self.folder = paths[0]
            else:
                self.files = list(paths)
            self.update_selection()
            self.selection.setToolTip("\n".join(map(str, paths)))
            self.reset_results(preview_folder=False)
            QTimer.singleShot(0, self.start)

    def tr_message(self, message, **values):
        return translate(self.language_code, message, **values)

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and hasattr(self, "taskbar"):
            self.taskbar.native_event(message)
        # Calling the base implementation here crashes with Linux/XCB in PyQt6.
        return False, 0

    def update_progress(self, completed):
        self.progress.setValue(completed)
        self.taskbar.update(completed, self.progress.maximum(), active=True)

    def set_status(self, message, values=None):
        self.status_message = (message, values or {})
        self.status.setText(self.tr_message(message, **self.status_message[1]))

    def update_selection(self):
        if self.folder is not None:
            text = self.tr_message(
                "Folder: {path} (including subfolders; symbolic links skipped)"
                if self.recursive.isChecked() else
                "Folder: {path} (without subfolders; symbolic links skipped)", path=self.folder
            )
        elif self.files:
            text = self.tr_message("{count} file(s) selected", count=len(self.files))
        else:
            text = self.tr_message("Select files or a folder to begin, or drag-and-drop files onto the the table or the executable itself.")
        self.selection.setText(text)

    def retranslate_ui(self):
        app = QApplication.instance()
        app.removeTranslator(self.qt_translator)
        language = self.language_code
        if language != "en" and self.qt_translator.load(
            f"qtbase_{language}",
            QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath),
        ):
            app.installTranslator(self.qt_translator)
        self.setWindowTitle(self.tr_message("Checksum Calculator") + " " + VERSION)
        self.algorithm_label.setText(self.tr_message("Algorithm:"))
        self.algorithm.setAccessibleName(self.tr_message("Checksum algorithm"))
        for widget, message in (
            (self.select_files, "Select files…"), (self.select_folder, "Select folder…"),
            (self.copy, "Copy results"), (self.save, "Save results…"),
            (self.compare, "Load and compare…"),
            (self.copy_checksums_action, "Copy checksums"),
        ):
            widget.setText(self.tr_message(message))
        self.calculate.setText(self.tr_message("Calculate"))
        self.recursive.setText(self.tr_message("Include subfolders"))
        self.auto_save.setText(self.tr_message("Save checksums automatically after completion as"))
        self.auto_save_name.setAccessibleName(self.tr_message("Checksum file name"))
        self.auto_save_name.setToolTip(self.tr_message(
            "Saved in the selected folder, or next to the first selected file"))
        self.table.setHorizontalHeaderLabels([
            self.tr_message("File"), self.algorithm.currentText(), self.tr_message("Status")
        ])
        self.update_selection()
        self.set_status(*self.status_message)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 2)
            message = item.data(Qt.ItemDataRole.UserRole)
            # OS error messages are already localized by the operating system.
            text = self.tr_message(message) if message in ("OK", "Cancelled") else message
            item.setText(text)
            item.setToolTip(text)

    def algorithm_changed(self, name):
        # Follow the algorithm unless the user chose a custom file name.
        if self.auto_save_name.text().strip() in ("", default_auto_save_name(self.current_algorithm)):
            self.auto_save_name.setText(default_auto_save_name(name))
        self.current_algorithm = name
        self.table.setHorizontalHeaderLabels([self.tr_message("File"), name, self.tr_message("Status")])
        self.save_settings()
        self.reset_results()

    def recursive_toggled(self):
        self.update_selection()
        self.save_settings()
        if self.folder is not None:
            self.reset_results()

    def auto_save_toggled(self, checked):
        self.auto_save_name.setEnabled(checked)
        self.save_settings()

    def save_settings(self):
        if self.settings_loaded:
            save_config({
                "algorithm": self.algorithm.currentText().lower(),
                "recursive": self.recursive.isChecked(),
                "auto_save": self.auto_save.isChecked(),
                "auto_save_name": self.auto_save_name.text().strip(),
            })

    def auto_save_path(self) -> Path | None:
        if not self.auto_save.isChecked():
            return None
        name = self.auto_save_name.text().strip() or default_auto_save_name(self.algorithm.currentText())
        if self.folder is not None:
            return self.folder / name
        return self.files[0].parent / name if self.files else None

    def excluded_path(self) -> Path | None:
        return self.auto_save_path() if self.folder is not None else None

    def remove_result(self, path):
        row = self.result_rows.pop(path, None)
        if row is None:
            return
        self.table.removeRow(row)
        for other, other_row in self.result_rows.items():
            if other_row > row:
                self.result_rows[other] = other_row - 1

    def choose_files(self):
        names, _ = QFileDialog.getOpenFileNames(self, self.tr_message("Select files"))
        if names:
            self.files = list(dict.fromkeys(Path(name) for name in names))
            self.folder = None
            self.update_selection()
            self.selection.setToolTip("\n".join(map(str, self.files)))
            self.reset_results()

    def select_dropped_paths(self, paths):
        if self.worker is not None:
            return
        self.folder = paths[0] if len(paths) == 1 and paths[0].is_dir() else None
        self.files = [] if self.folder is not None else paths
        self.update_selection()
        self.selection.setToolTip("\n".join(map(str, paths)))
        self.reset_results()

    def choose_folder(self):
        name = QFileDialog.getExistingDirectory(self, self.tr_message("Select folder"))
        if name:
            self.folder = Path(name)
            self.files = []
            self.update_selection()
            self.selection.setToolTip(name)
            self.reset_results()

    def reset_results(self, preview_folder=True):
        self.taskbar.update()
        self.preview_files = None
        pending_paths = list(self.files)
        if self.folder is not None and not preview_folder:
            pending_paths.extend(Path(path) for path in self.result_rows if Path(path) not in pending_paths)
        self.table.setRowCount(0)
        self.result_rows.clear()
        for path in pending_paths:
            self.add_result(str(path), "", "")
        self.copy.setEnabled(False)
        self.save.setEnabled(False)
        self.compare.setEnabled(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.calculate.setEnabled(bool(self.files) or self.folder is not None)
        self.set_status("Ready")
        if self.folder is not None and preview_folder:
            for widget in (self.select_files, self.select_folder, self.algorithm, self.recursive):
                widget.setEnabled(False)
            self.calculate.setText(self.tr_message("Cancel"))
            self.progress.setRange(0, 0)
            self.set_status("Discovering files…")
            self.preview_files = []
            self.worker = ChecksumWorker(list(self.files), self.folder, self, preview_only=True,
                                         exclude=self.excluded_path(), recursive=self.recursive.isChecked())
            self.worker.result.connect(self.add_preview_result)
            self.worker.summary.connect(self.set_status)
            self.worker.finished.connect(self.preview_finished)
            self.worker.start()

    def add_preview_result(self, path, digest, status):
        if not status:
            self.preview_files.append(Path(path))
        self.add_result(path, digest, status)

    def preview_finished(self):
        self.worker.deleteLater()
        self.worker = None
        for widget in (self.select_files, self.select_folder, self.algorithm, self.calculate, self.recursive):
            widget.setEnabled(True)
        self.calculate.setText(self.tr_message("Calculate"))
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        if self.close_pending:
            self.close()

    def toggle_calculation(self):
        if self.worker is None:
            self.start()
        else:
            self.stop()

    def start(self):
        files = list(self.preview_files if self.preview_files is not None else self.files)
        folder = self.folder if self.preview_files is None else None
        excluded = self.excluded_path()
        if excluded is not None and excluded in files:
            # Auto-save was enabled or renamed after the folder had been listed.
            files.remove(excluded)
            if self.preview_files is not None:
                self.preview_files.remove(excluded)
            self.remove_result(str(excluded))
        for row in range(self.table.rowCount()):
            for column in (1, 2):
                item = self.table.item(row, column)
                item.setText("")
                item.setToolTip("")
                item.setData(Qt.ItemDataRole.UserRole, "")
        for button in (self.copy, self.save, self.compare):
            button.setEnabled(False)
        for button in (self.select_files, self.select_folder, self.algorithm, self.recursive):
            button.setEnabled(False)
        self.calculate.setText(self.tr_message("Cancel"))
        self.progress.setRange(0, 0)
        self.taskbar.update(total=0, active=True)
        if folder is not None:
            self.set_status("Discovering files…")
        else:
            self.set_total(len(files))
        self.worker = ChecksumWorker(
            files, folder, self, algorithm=self.algorithm.currentText().lower(), exclude=excluded,
            recursive=self.recursive.isChecked(),
        )
        self.worker.discovered.connect(self.set_total)
        self.worker.result.connect(self.add_result)
        self.worker.progress.connect(self.update_progress)
        self.worker.summary.connect(self.set_status)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def set_total(self, total):
        self.progress.setRange(0, max(total, 1))
        self.update_progress(0)
        self.set_status("Calculating {algorithm} for {count} file(s)…", dict(algorithm=self.algorithm.currentText(), count=total))

    def add_result(self, path, digest, status):
        row = self.result_rows.get(path)
        if row is None:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.result_rows[path] = row
        file_path = Path(path)
        display_path = file_path.name
        if self.folder is not None:
            try:
                display_path = str(file_path.relative_to(self.folder))
            except ValueError:
                pass
        for column, value in enumerate((display_path, digest, status)):
            if column == 2 and status in ("OK", "Cancelled"):
                value = self.tr_message(status)
            item = QTableWidgetItem(value)
            if column == 2:
                item.setData(Qt.ItemDataRole.UserRole, status)
            item.setToolTip(path if column == 0 else value)
            if column == 0:
                item.setData(Qt.ItemDataRole.UserRole, path)
            self.table.setItem(row, column, item)

    def stop(self):
        if self.worker:
            self.worker.requestInterruption()
            self.calculate.setText(self.tr_message("Cancelling…"))
            self.calculate.setEnabled(False)
            self.set_status("Cancelling…")

    def finished(self):
        self.auto_save_results()
        message, values = self.status_message
        if not self.close_pending and not self.isActiveWindow():
            self.notifications.show(
                self.tr_message("Checksum Calculator"), self.tr_message(message, **values)
            )
        self.taskbar.update()
        self.worker.deleteLater()
        self.worker = None
        for button in (self.select_files, self.select_folder, self.calculate, self.algorithm, self.recursive):
            button.setEnabled(True)
        self.calculate.setText(self.tr_message("Calculate"))
        self.copy.setEnabled(self.table.rowCount() > 0)
        self.save.setEnabled(bool(self.results_text()))
        self.compare.setEnabled(self.table.rowCount() > 0)
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 1)
        if self.close_pending:
            self.close()

    def auto_save_results(self):
        message, values = self.status_message
        path = self.auto_save_path()
        text = self.results_text()
        if path is None or not text or message != FINISHED_MESSAGE or self.close_pending:
            return
        try:
            write_results(path, text)
        except OSError as error:
            self.set_status(FINISHED_MESSAGE + " Could not save checksums to {path}: {error}",
                            dict(values, path=path, error=error))
        else:
            self.set_status(FINISHED_MESSAGE + " Checksums saved to {path}", dict(values, path=path))

    def results_text(self):
        rows = []
        for row in range(self.table.rowCount()):
            path = self.table.item(row, 0).text()
            digest = self.table.item(row, 1).text()
            if digest:
                rows.append(f"{digest}  {path}")
        return "\n".join(rows)

    def copy_selected_checksums(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        checksums = [self.table.item(row, 1).text() for row in rows]
        text = "\n".join(checksum for checksum in checksums if checksum)
        if text:
            QApplication.clipboard().setText(text)

    def copy_results(self):
        QApplication.clipboard().setText(self.results_text())

    def save_results(self):
        text = self.results_text()
        if not text:
            return
        name, _ = QFileDialog.getSaveFileName(
            self, self.tr_message("Save checksum results"),
            f"checksums-{self.algorithm.currentText().lower()}.txt",
            self.tr_message("Text files (*.txt);;All files (*)"),
        )
        if not name:
            return
        try:
            write_results(Path(name), text)
        except OSError as error:
            QMessageBox.warning(self, self.tr_message("Could not save results"), str(error))
            return
        self.set_status("Results saved to {path}", dict(path=name))

    def load_and_compare(self):
        if self.worker is not None or not self.table.rowCount():
            return
        name, _ = QFileDialog.getOpenFileName(
            self, self.tr_message("Load saved checksum results"), "",
            self.tr_message("Text files (*.txt);;All files (*)"),
        )
        if not name:
            return
        try:
            algorithm, saved = parse_results(Path(name).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError) as error:
            QMessageBox.warning(self, self.tr_message("Could not load results"),
                                self.tr_message(str(error)) if type(error) is ValueError else str(error))
            return
        if algorithm != self.algorithm.currentText():
            QMessageBox.warning(
                self, self.tr_message("Cannot compare results"),
                self.tr_message("Saved results use {saved}; current results use {current}.",
                                saved=algorithm, current=self.algorithm.currentText()),
            )
            return
        current = [(self.table.item(row, 0).text(), self.table.item(row, 1).text())
                   for row in range(self.table.rowCount())]
        rows = compare_results(current, saved)
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr_message("Compare results"))
        dialog.resize(1100, 600)
        layout = QVBoxLayout(dialog)
        source = QLabel(self.tr_message("Saved results: {path}", path=name))
        source.setWordWrap(True)
        layout.addWidget(source)
        table = QTableWidget(len(rows), 4, dialog)
        table.setHorizontalHeaderLabels([self.tr_message(label) for label in
                                        ("File", "Current checksum", "Saved checksum", "Comparison")])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(self.tr_message(value) if column == 3 else value)
                item.setToolTip(item.text())
                table.setItem(row, column, item)
        table.setColumnWidth(0, 250)
        table.setColumnWidth(1, 300)
        table.setColumnWidth(2, 300)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSortingEnabled(True)
        layout.addWidget(table)
        summary = []
        for status in dict.fromkeys(row[3] for row in rows):
            summary.append(f"{self.tr_message(status)}: {sum(row[3] == status for row in rows)}")
        label = QLabel(" · ".join(summary))
        label.setWordWrap(True)
        layout.addWidget(label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
        dialog.deleteLater()

    def closeEvent(self, event):
        if self.worker is not None:
            self.close_pending = True
            self.stop()
            event.ignore()
        else:
            self.taskbar.update()
            event.accept()


if __name__ == "__main__":
    args = parse_arguments()
    app = QApplication([sys.argv[0]])
    window = MainWindow(args.paths, args.algorithm)
    window.show()
    sys.exit(app.exec())
