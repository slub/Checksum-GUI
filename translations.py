"""UI message catalogs. Add a catalog and a LANGUAGES entry for another language.

English source messages are the fallback. Keep named format placeholders intact.
"""

LANGUAGES = {"en": "English", "de": "Deutsch"}
CATALOGS = {
    "de": {
        "Checksum Calculator": "Prüfsummenrechner",
        "Language:": "Sprache:",
        "Select files…": "Dateien auswählen…",
        "Select folder…": "Ordner auswählen…",
        "Select files": "Dateien auswählen",
        "Select folder": "Ordner auswählen",
        "Checksum algorithm": "Prüfsummenalgorithmus",
        "Algorithm:": "Algorithmus:",
        "Calculate": "Berechnen",
        "Cancel": "Abbrechen",
        "Cancelling…": "Wird abgebrochen…",
        "Copy results": "Ergebnisse kopieren",
        "Save results…": "Ergebnisse speichern…",
        "Load and compare…": "Laden und vergleichen…",
        "Load saved checksum results": "Gespeicherte Prüfsummenergebnisse laden",
        "Could not load results": "Ergebnisse konnten nicht geladen werden",
        "Cannot compare results": "Ergebnisse können nicht verglichen werden",
        "Saved results use {saved}; current results use {current}.": "Gespeicherte Ergebnisse verwenden {saved}; aktuelle Ergebnisse verwenden {current}.",
        "Compare results": "Ergebnisse vergleichen",
        "Saved results: {path}": "Gespeicherte Ergebnisse: {path}",
        "Current checksum": "Aktuelle Prüfsumme",
        "Saved checksum": "Gespeicherte Prüfsumme",
        "Comparison": "Vergleich",
        "Match": "Übereinstimmung",
        "Different": "Abweichend",
        "Current only": "Nur aktuell",
        "Saved only": "Nur gespeichert",
        "Not calculated": "Nicht berechnet",
        "Ambiguous filename": "Mehrdeutiger Dateiname",
        "Invalid results file. Expected checksum, two spaces, and file path on each line.": "Ungültige Ergebnisdatei. Jede Zeile muss eine Prüfsumme, zwei Leerzeichen und einen Dateipfad enthalten.",
        "The results file contains multiple checksum algorithms.": "Die Ergebnisdatei enthält mehrere Prüfsummenalgorithmen.",
        "The results file contains no checksums.": "Die Ergebnisdatei enthält keine Prüfsummen.",
        "Copy checksums": "Prüfsummen kopieren",
        "Select files or a folder to begin, or drag-and-drop files onto the the table or the executable itself.": "Wählen Sie Dateien oder einen Ordner aus, oder ziehen Sie Dateien per Drag-and-Drop auf die Tabelle oder die ausführbare Datei.",
        "File": "Datei",
        "Status": "Status",
        "Ready": "Bereit",
        "{count} file(s) selected": "{count} Datei(en) ausgewählt",
        "Folder: {path} (including subfolders; symbolic links skipped)": "Ordner: {path} (einschließlich Unterordner; symbolische Links werden übersprungen)",
        "Discovering files…": "Dateien werden gesucht…",
        "Calculating {algorithm} for {count} file(s)…": "{algorithm} wird für {count} Datei(en) berechnet…",
        "OK": "OK",
        "Cancelled": "Abgebrochen",
        "Finished: {completed} file(s) calculated, {errors} error(s).": "Fertig: {completed} Datei(en) berechnet, {errors} Fehler.",
        "Cancelled: {completed} file(s) calculated, {errors} error(s).": "Abgebrochen: {completed} Datei(en) berechnet, {errors} Fehler.",
        "Calculation failed: {error}": "Berechnung fehlgeschlagen: {error}",
        "Save checksum results": "Prüfsummenergebnisse speichern",
        "Text files (*.txt);;All files (*)": "Textdateien (*.txt);;Alle Dateien (*)",
        "Could not save results": "Ergebnisse konnten nicht gespeichert werden",
        "Results saved to {path}": "Ergebnisse gespeichert unter {path}",
    }
}


def translate(language: str, message: str, **values) -> str:
    return CATALOGS.get(language, {}).get(message, message).format(**values)
