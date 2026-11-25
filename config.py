"""Persist user settings in a JSON file in the user's configuration directory."""

import json
import os
import sys
from pathlib import Path


def config_directory() -> Path:
    """%APPDATA% (Roaming) on Windows, $XDG_CONFIG_HOME or ~/.config elsewhere."""
    variable = "APPDATA" if sys.platform == "win32" else "XDG_CONFIG_HOME"
    directory = os.environ.get(variable)
    return Path(directory) if directory else Path.home() / (
        "AppData/Roaming" if sys.platform == "win32" else ".config")


CONFIG_PATH = config_directory() / "chksmg.json"
ALGORITHMS = ("sha512", "sha1", "md5")


def default_auto_save_name(algorithm: str) -> str:
    return f"checksums.{algorithm.lower()}"


def load_config() -> dict:
    """Return validated settings; missing or invalid values fall back to defaults."""
    config = {"algorithm": "sha512", "auto_save": False, "auto_save_name": ""}
    try:
        stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
    if str(stored.get("algorithm", "")).lower() in ALGORITHMS:
        config["algorithm"] = stored["algorithm"].lower()
    if isinstance(stored.get("auto_save"), bool):
        config["auto_save"] = stored["auto_save"]
    if isinstance(stored.get("auto_save_name"), str):
        config["auto_save_name"] = stored["auto_save_name"].strip()
    if not config["auto_save_name"]:
        config["auto_save_name"] = default_auto_save_name(config["algorithm"])
    return config


def save_config(config: dict) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8", newline="\n")
    except OSError:
        pass
