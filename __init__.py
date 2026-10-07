"""QGIS entry point for OuvreRaccourcis."""

from __future__ import annotations

import configparser
import shutil
from pathlib import Path


PLUGIN_NAME = "OuvreRaccourcis"


def _normalise_plugin_dir_name(name: str) -> str:
    """Return a comparison key suitable for legacy plugin folder names."""
    return "".join(character.lower() for character in name if character.isalnum())


def _is_legacy_installation(candidate: Path, current_dir: Path) -> bool:
    """Return True only for another OuvreRaccourcis plugin installation."""
    try:
        if candidate.resolve() == current_dir.resolve():
            return False
    except OSError:
        if candidate == current_dir:
            return False

    if not candidate.is_dir():
        return False

    if not _normalise_plugin_dir_name(candidate.name).startswith("ouvreraccourcis"):
        return False

    metadata_path = candidate / "metadata.txt"
    if not metadata_path.is_file():
        return False

    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(metadata_path, encoding="utf-8-sig")
        plugin_name = parser.get("general", "name", fallback="").strip()
    except (OSError, configparser.Error):
        return False

    return plugin_name.casefold() == PLUGIN_NAME.casefold()


def _remove_legacy_installations() -> list[tuple[str, str]]:
    """Remove obsolete sibling installations of this same plugin.

    This handles ZIPs that were previously installed under a versioned or
    differently-cased directory name.  Failures are returned to the caller and
    never prevent the current plugin from loading.
    """
    current_dir = Path(__file__).resolve().parent
    plugins_dir = current_dir.parent
    failures: list[tuple[str, str]] = []

    try:
        candidates = list(plugins_dir.iterdir())
    except OSError as exc:
        return [(str(plugins_dir), str(exc))]

    for candidate in candidates:
        if not _is_legacy_installation(candidate, current_dir):
            continue
        try:
            shutil.rmtree(candidate)
        except OSError as exc:
            failures.append((str(candidate), str(exc)))

    return failures


def classFactory(iface):
    # Clean up legacy duplicate folders before creating the new plugin GUI.
    # QGIS' ZIP installer overwrites the canonical folder but cannot reliably
    # remove older installations that used a different top-level folder name.
    cleanup_failures = _remove_legacy_installations()

    from .plugin import OuvreRaccourcisPlugin

    return OuvreRaccourcisPlugin(iface, cleanup_failures=cleanup_failures)
