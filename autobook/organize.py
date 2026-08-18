from __future__ import annotations

from pathlib import Path

from pathvalidate import sanitize_filename


def sanitize(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "libro"
    return sanitize_filename(name, replacement_text="_")


def normalize_author(author: str) -> str:
    """Normaliza autores como vienen de Anna's Archive:
    - 'Apellido, Nombre' -> 'Nombre Apellido' (el orden que Calibre parsea bien).
    - 'Autor; Contribuidor' -> solo el primer autor (Anna's lista distribuidores,
      narradores, etc. tras punto y coma).
    Solo transforma casos sin ambigüedad."""
    a = (author or "").strip()
    if not a:
        return a
    if ";" in a:
        a = a.split(";", 1)[0].strip()
    if "&" in a or " and " in a.lower():
        return a
    if a.count(",") == 1:
        last, first = (p.strip() for p in a.split(",", 1))
        if last and first:
            return f"{first} {last}"
    return a


_ARTICLES = {
    "en": ("the", "a", "an"),
    "es": ("el", "la", "los", "las", "un", "una", "unos", "unas"),
    "fr": ("le", "la", "les", "un", "une"),
    "de": ("der", "die", "das", "ein", "eine"),
    "it": ("il", "lo", "la", "i", "gli", "le", "un", "una"),
    "pt": ("o", "a", "os", "as", "um", "uma"),
}
_DEFAULT_ARTICLES = ("the", "a", "an")


def compute_title_sort(title: str, language: str = "") -> str:
    """Réplica simple del title_sort de Calibre: mueve el artículo inicial al final."""
    t = (title or "").strip()
    if not t:
        return t
    articles = _ARTICLES.get((language or "").lower()[:2], _DEFAULT_ARTICLES)
    head, sep, rest = t.partition(" ")
    if sep and head.lower() in articles:
        return f"{rest}, {head}"
    return t


def compute_author_sort(author: str) -> str:
    """Réplica simple del author_sort de Calibre: 'Nombre Apellido' -> 'Apellido, Nombre'."""
    a = (author or "").strip()
    if not a or "," in a:
        return a
    if " & " in a:
        return " & ".join(compute_author_sort(p.strip()) for p in a.split(" & "))
    parts = a.split()
    if len(parts) == 1:
        return a
    return f"{parts[-1]}, {' '.join(parts[:-1])}"


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