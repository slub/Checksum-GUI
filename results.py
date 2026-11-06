"""Read exported checksum results and compare them without touching files."""

import re
from collections import Counter


def parse_results(text):
    records = []
    algorithm = None
    for line in text.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-fA-F]+)  (.+)", line)
        if match is None or len(match[1]) not in (32, 40, 128):
            raise ValueError("Invalid results file. Expected checksum, two spaces, and file path on each line.")
        current_algorithm = {32: "MD5", 40: "SHA1", 128: "SHA512"}[len(match[1])]
        if algorithm is not None and current_algorithm != algorithm:
            raise ValueError("The results file contains multiple checksum algorithms.")
        algorithm = current_algorithm
        records.append((match[2], match[1].lower()))
    if not records:
        raise ValueError("The results file contains no checksums.")
    return algorithm, records


def compare_results(current, saved):
    """Return (path, current checksum, saved checksum, status) rows.

    Duplicate display paths cannot identify a file reliably, even if hashes match.
    """
    current_counts = Counter(path for path, _ in current)
    saved_counts = Counter(path for path, _ in saved)
    current_map, saved_map = dict(current), dict(saved)
    rows = []
    for path in dict.fromkeys([*current_map, *saved_map]):
        actual, expected = current_map.get(path, ""), saved_map.get(path, "")
        if current_counts[path] > 1 or saved_counts[path] > 1:
            status = "Ambiguous filename"
        elif path not in current_map:
            status = "Saved only"
        elif path not in saved_map:
            status = "Current only"
        elif not actual:
            status = "Not calculated"
        elif actual.lower() == expected.lower():
            status = "Match"
        else:
            status = "Different"
        rows.append((path, actual, expected, status))
    return rows
