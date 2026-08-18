from __future__ import annotations

from pathlib import Path

from pathvalidate import sanitize_filename


def sanitize(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "libro"
    return sanitize_filename(name, replacement_text="_")


def _format_series_index(value: int | float) -> str:
    f = float(value)
    if f.is_integer():
        return f"{int(f):02d}"
    return f"{f:.1f}"


def build_destination(
    download_dir: Path,
    title: str,
    author: str,
    ext: str,
    overwrite: bool = False,
    series: str | None = None,
    series_index: int | float | None = None,
) -> Path:
    ext = ext.lstrip(".").lower() or "epub"
    if series:
        folder = download_dir / sanitize(series)
        if series_index is not None:
            base = f"Book {_format_series_index(series_index)} - {sanitize(title)}"
        else:
            base = sanitize(title)
    else:
        folder = download_dir / (sanitize(author) if author else "Sin autor")
        base = sanitize(title)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{base}.{ext}"
    if not overwrite:
        counter = 1
        while dest.exists():
            dest = folder / f"{base} ({counter}).{ext}"
            counter += 1
    return dest