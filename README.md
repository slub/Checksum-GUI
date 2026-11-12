# Checksum Calculator GUI

An intuitive Python 3.10+/Qt6 desktop app for calculating SHA512, SHA1 or MD5
checksums of multiple files or all files inside a directory.
Changing the algorithm or selecting new files/folder clears previous results.
Selecting a folder scans it in the background and lists its files, including subfolders, before you click Calculate. Symbolic links are skipped.

Pass files or one folder on the command line to start calculating automatically:

```sh
python3 main.py file1.iso "file with spaces.zip"
python3 main.py --algorithm sha1 ./folder
```

On Windows, you can drag and drop files onto the with PyInstaller compiled
.exe file to make use of this feature. Windows then starts the program
with the dropped file paths as command line parameters automatically.

Use `--algorithm sha512`, `--algorithm sha1`, or `--algorithm md5` (also `-a`)
to choose the algorithm. Use `--` before filenames that begin with a dash.
With no paths, the app waits for a manual selection.

The interface automatically uses the operating system's language at startup.
Unsupported languages fall back to English.

Translations live in `translations.py`. To add a language, add its code and name
to `LANGUAGES` and a message dictionary to `CATALOGS`, preserving placeholders
such as `{algorithm}`.

Hashing runs in a background thread and reads files in 1 MiB chunks. Progress
counts processed files. Cancel preserves completed results; unreadable files
show an error and do not stop the remaining work. Copy results copies successful
checksums and the file path to the clipboard. Avoid modifying files during hashing.

"Save results…" exports successful checksums and the paths displayed in the table
to a UTF-8 text file, one result per line. Selected files use filenames only;
folder results use paths relative to the selected folder.

After calculating, use "Load and compare…" to open a previously saved results
file. Both sets must use the same algorithm. Paths are matched exactly as displayed,
including case and path separators; duplicate filenames are marked ambiguous.
Only completed results are available after cancelling a calculation,
so "Saved only" does not necessarily mean a file was deleted.

## Tests

Run checks with `QT_QPA_PLATFORM=offscreen python3 -m unittest -v`.
