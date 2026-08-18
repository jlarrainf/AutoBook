"""Integración con Calibre: importar libros a la biblioteca y enviarlos al dispositivo.

Usa calibredb/ebook-convert (incluidos con Calibre) y lectura directa de
metadata.db (solo lectura) para localizar libros sin depender del idioma de la
salida de calibredb.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import string
import subprocess
import tempfile
from pathlib import Path

from .config import CalibreConfig
from .organize import sanitize

CALIBREDB_CANDIDATES = [
    Path("C:/Program Files/Calibre2/calibredb.exe"),
    Path("C:/Program Files (x86)/Calibre2/calibredb.exe"),
]

SOURCE_FORMAT_PREFERENCE = ("EPUB", "AZW3", "MOBI", "PDF", "FB2", "TXT")

MTP_LIST_PS = (
    "$shell = New-Object -ComObject Shell.Application;"
    "$shell.Namespace(17).Items() | ForEach-Object { $_.Name }"
)

MTP_COPY_PS = r"""
param([string]$DeviceName, [string]$SubFolder, [string]$FilePath, [string]$DestName, [int]$TimeoutS = 600)
$shell = New-Object -ComObject Shell.Application
$dev = $shell.Namespace(17).Items() | Where-Object { $_.Name -eq $DeviceName } | Select-Object -First 1
if (-not $dev) { Write-Output "ERROR:DEVICE_NOT_FOUND"; exit 2 }
$folder = $dev.GetFolder
$storage = $folder.Items() | Where-Object { $_.Name -like 'Internal*' } | Select-Object -First 1
if ($storage) { $folder = $storage.GetFolder }
if ($SubFolder) {
  $sub = $folder.Items() | Where-Object { $_.Name -eq $SubFolder } | Select-Object -First 1
  if (-not $sub) { Write-Output "ERROR:SUBFOLDER_NOT_FOUND"; exit 3 }
  $folder = $sub.GetFolder
}
# MoveHere es asíncrono y no renombra: el archivo ya viene con el nombre final.
$folder.MoveHere($FilePath, 0x14)
$deadline = (Get-Date).AddSeconds($TimeoutS)
while ((Get-Date) -lt $deadline) {
  $item = $folder.Items() | Where-Object { $_.Name -eq $DestName } | Select-Object -First 1
  if ($item) { Write-Output "OK"; exit 0 }
  Start-Sleep -Seconds 2
}
Write-Output "ERROR:TIMEOUT"; exit 4
"""


class CalibreError(RuntimeError):
    pass


def _no_window_flags() -> int:
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
    return 0


def find_calibredb(cfg: CalibreConfig) -> Path | None:
    if cfg.calibredb:
        p = Path(cfg.calibredb).expanduser()
        return p if p.exists() else None
    env = os.getenv("CALIBRE_DB")
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return p
    for p in CALIBREDB_CANDIDATES:
        if p.exists():
            return p
    found = shutil.which("calibredb")
    return Path(found) if found else None


def find_library_path(cfg: CalibreConfig) -> Path | None:
    if cfg.library_path:
        return Path(cfg.library_path).expanduser()
    appdata = os.getenv("APPDATA") or os.getenv("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    gp = Path(appdata) / "calibre" / "global.py.json"
    if gp.exists():
        try:
            data = json.loads(gp.read_text(encoding="utf-8"))
            lp = data.get("library_path")
            if lp:
                return Path(lp)
        except Exception:
            pass
    return None


def is_gui_open() -> bool:
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq calibre.exe", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=_no_window_flags(),
            ).stdout
            return "calibre.exe" in out.lower()
        r = subprocess.run(["pgrep", "-x", "calibre"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


class CalibreIntegration:
    def __init__(self, cfg: CalibreConfig) -> None:
        self.cfg = cfg
        self.calibredb = find_calibredb(cfg)
        self.library = find_library_path(cfg)

    # -- estado --

    def available(self) -> bool:
        return bool(
            self.cfg.enabled
            and self.calibredb
            and self.library
            and (self.library / "metadata.db").exists()
        )

    def status(self) -> dict:
        device = self.detect_device()
        return {
            "enabled": self.cfg.enabled,
            "calibredb": str(self.calibredb) if self.calibredb else None,
            "library_path": str(self.library) if self.library else None,
            "library_exists": bool(self.library and (self.library / "metadata.db").exists()),
            "gui_open": is_gui_open(),
            "device_format": self.cfg.device_format,
            "device": device,
        }

    def _require(self) -> None:
        if not self.cfg.enabled:
            raise CalibreError("Integración con Calibre desactivada (calibre.enabled=false).")
        if not self.calibredb:
            raise CalibreError("No se encontró calibredb. Instala Calibre o define calibre.calibredb / CALIBRE_DB.")
        if not self.library or not (self.library / "metadata.db").exists():
            raise CalibreError(
                "No se encontró la biblioteca de Calibre. Define calibre.library_path o CALIBRE_LIBRARY."
            )

    # -- calibredb --

    def _run_calibredb(self, args: list[str], timeout: int = 300) -> str:
        cmd = [str(self.calibredb), "--with-library", str(self.library), *args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=_no_window_flags(),
            )
        except FileNotFoundError:
            raise CalibreError(f"calibredb no ejecutable: {self.calibredb}")
        except subprocess.TimeoutExpired:
            raise CalibreError(f"calibredb {args[0] if args else ''} agotó el tiempo (>{timeout}s)")
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            hint = ""
            if "lock" in err.lower():
                hint = " La base de datos está bloqueada: cierra la GUI de Calibre y reintenta."
            raise CalibreError(f"calibredb falló (rc={result.returncode}): {err[:500]}{hint}")
        return result.stdout

    # -- metadata.db (solo lectura) --

    def _connect_ro(self) -> sqlite3.Connection:
        db = self.library / "metadata.db"
        return sqlite3.connect(f"file:{db}?mode=ro", uri=True)

    def find_by_identifier(self, id_type: str, value: str) -> int | None:
        try:
            with self._connect_ro() as conn:
                row = conn.execute(
                    "SELECT book FROM identifiers WHERE type=? AND val=? LIMIT 1",
                    (id_type, value),
                ).fetchone()
            return row[0] if row else None
        except sqlite3.Error:
            return None

    def _max_book_id(self) -> int:
        try:
            with self._connect_ro() as conn:
                row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM books").fetchone()
            return row[0]
        except sqlite3.Error:
            return 0

    def _new_book_id_since(self, prev_max: int) -> int | None:
        try:
            with self._connect_ro() as conn:
                row = conn.execute(
                    "SELECT id FROM books WHERE id > ? ORDER BY id LIMIT 1", (prev_max,)
                ).fetchone()
            return row[0] if row else None
        except sqlite3.Error:
            return None

    def find_by_title_author(self, title: str, author: str) -> int | None:
        try:
            with self._connect_ro() as conn:
                row = conn.execute(
                    """
                    SELECT b.id FROM books b
                    WHERE lower(b.title) = lower(?)
                    ORDER BY b.id DESC LIMIT 1
                    """,
                    (title,),
                ).fetchone()
                if row:
                    return row[0]
                if author:
                    row = conn.execute(
                        """
                        SELECT b.id FROM books b
                        JOIN books_authors_link bal ON bal.book = b.id
                        JOIN authors a ON a.id = bal.author
                        WHERE lower(b.title) LIKE '%' || lower(?) || '%'
                          AND lower(a.name) LIKE '%' || lower(?) || '%'
                        ORDER BY b.id DESC LIMIT 1
                        """,
                        (title, author),
                    ).fetchone()
                    return row[0] if row else None
        except sqlite3.Error:
            return None
        return None

    def book_formats(self, book_id: int) -> dict[str, Path]:
        """Formatos de un libro en la biblioteca: {FORMAT: ruta del archivo}."""
        out: dict[str, Path] = {}
        try:
            with self._connect_ro() as conn:
                rows = conn.execute(
                    """
                    SELECT d.format, b.path, d.name
                    FROM data d JOIN books b ON b.id = d.book
                    WHERE d.book = ?
                    """,
                    (book_id,),
                ).fetchall()
            for fmt, relpath, name in rows:
                out[fmt.upper()] = self.library / relpath / f"{name}.{fmt.lower()}"
        except sqlite3.Error as exc:
            raise CalibreError(f"Error leyendo metadata.db: {exc}")
        return out

    def book_title_author(self, book_id: int) -> tuple[str, str]:
        try:
            with self._connect_ro() as conn:
                row = conn.execute("SELECT title FROM books WHERE id = ?", (book_id,)).fetchone()
                title = row[0] if row else ""
                rows = conn.execute(
                    """
                    SELECT a.name FROM authors a
                    JOIN books_authors_link l ON l.author = a.id
                    WHERE l.book = ? ORDER BY a.name
                    """,
                    (book_id,),
                ).fetchall()
            return title, " & ".join(r[0] for r in rows)
        except sqlite3.Error:
            return "", ""

    # -- importar --

    def add_book(
        self,
        file_path: Path | str,
        title: str = "",
        author: str = "",
        language: str = "",
        series: str | None = None,
        series_index: int | float | None = None,
        identifier_md5: str = "",
    ) -> dict:
        self._require()
        file_path = Path(file_path)
        if not file_path.exists():
            raise CalibreError(f"Archivo no encontrado: {file_path}")

        if identifier_md5:
            existing = self.find_by_identifier("annas", identifier_md5)
            if existing:
                return {"book_id": existing, "duplicated": True, "library": str(self.library)}

        args = ["add", "--automerge=ignore"]
        if title:
            args += ["--title", title]
        if author:
            args += ["--authors", author]
        if language:
            args += ["--languages", language]
        if series:
            args += ["--series", series]
        if series_index is not None:
            args += ["--series-index", str(series_index)]
        if identifier_md5:
            args += ["--identifier", f"annas:{identifier_md5}"]
        args.append(str(file_path))

        prev_max = self._max_book_id()
        self._run_calibredb(args)

        if identifier_md5:
            book_id = self.find_by_identifier("annas", identifier_md5)
            if book_id and book_id > prev_max:
                return {"book_id": book_id, "duplicated": False, "library": str(self.library)}
            if book_id:
                return {"book_id": book_id, "duplicated": True, "library": str(self.library)}
        else:
            book_id = self._new_book_id_since(prev_max)
            if book_id:
                return {"book_id": book_id, "duplicated": False, "library": str(self.library)}

        # automerge descartó el archivo porque ya existía un libro con mismo
        # título/autor (sin nuestro identificador): localizarlo.
        book_id = self.find_by_title_author(title, author)
        if book_id:
            return {"book_id": book_id, "duplicated": True, "library": str(self.library)}
        return {"book_id": None, "duplicated": False, "library": str(self.library),
                "note": "calibredb añadió el libro pero no se pudo determinar el id."}

    def set_metadata(self, book_id: int, fields: dict[str, str]) -> None:
        """Fija campos (title, authors, languages, series...) recalculando los sort."""
        self._require()
        args = ["set_metadata", str(book_id)]
        for key, value in fields.items():
            args += ["-f", f"{key}:{value}"]
        self._run_calibredb(args)

    def embed_metadata(self, book_id: int, fmt: str = "") -> None:
        """Incrusta los metadatos de la BD en el archivo (necesario antes de
        convertir/enviar para que el dispositivo vea los metadatos corregidos)."""
        self._require()
        args = ["embed_metadata", str(book_id)]
        if fmt:
            args += ["--only-format", fmt]
        self._run_calibredb(args, timeout=600)

    # -- dispositivo --

    def detect_device(self) -> dict | None:
        if self.cfg.device_path:
            p = Path(self.cfg.device_path).expanduser()
            if p.exists():
                return {"type": "manual", "path": str(p), "dest_dir": str(p)}
            return None
        if os.name != "nt":
            return None
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            bitmask = kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if not bitmask & 1:
                    bitmask >>= 1
                    continue
                bitmask >>= 1
                if letter in ("A", "B", "C"):
                    continue
                root = Path(f"{letter}:\\")
                try:
                    if kernel32.GetDriveTypeW(str(root)) != 2:  # DRIVE_REMOVABLE
                        continue
                    if (root / "documents").is_dir():
                        return {"type": "kindle", "path": str(root), "dest_dir": str(root / "documents")}
                    if (root / ".kobo").exists():
                        return {"type": "kobo", "path": str(root), "dest_dir": str(root)}
                except OSError:
                    continue
        except Exception:
            pass
        return self._detect_mtp()

    def _detect_mtp(self) -> dict | None:
        """Dispositivos portátiles (MTP) visibles en 'Este equipo': Kindle/Kobo
        modernos que no se montan con letra de unidad."""
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", MTP_LIST_PS],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=_no_window_flags(),
            )
        except Exception:
            return None
        if r.returncode != 0:
            return None
        for line in r.stdout.splitlines():
            name = line.strip()
            if not name:
                continue
            low = name.lower()
            if "kindle" in low:
                return {"type": "kindle", "interface": "mtp", "path": name,
                        "name": name, "dest_dir": "documents"}
            if "kobo" in low:
                return {"type": "kobo", "interface": "mtp", "path": name,
                        "name": name, "dest_dir": ""}
        return None

    def _copy_to_mtp(self, device_name: str, subfolder: str, src: Path, dest_name: str,
                     timeout_s: int = 600) -> None:
        # Shell no renombra al mover a MTP: se prepara una copia con el nombre final.
        staging = Path(tempfile.gettempdir()) / "autobook_send"
        staging.mkdir(exist_ok=True)
        staged = staging / dest_name
        shutil.copy2(src, staged)
        script = Path(tempfile.gettempdir()) / f"autobook_mtp_{os.getpid()}.ps1"
        script.write_text(MTP_COPY_PS, encoding="utf-8")
        cmd = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
            "-DeviceName", device_name,
            "-SubFolder", subfolder or "",
            "-FilePath", str(staged),
            "-DestName", dest_name,
            "-TimeoutS", str(timeout_s),
        ]
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s + 60,
                creationflags=_no_window_flags(),
            )
        except subprocess.TimeoutExpired:
            raise CalibreError("El copiado al dispositivo MTP agotó el tiempo.")
        finally:
            script.unlink(missing_ok=True)
            staged.unlink(missing_ok=True)
        out = (r.stdout or "").strip()
        if r.returncode != 0 or not out.startswith("OK"):
            detail = out or (r.stderr or "").strip()[:300]
            if "DEVICE_NOT_FOUND" in detail:
                detail = "el dispositivo ya no está visible en 'Este equipo' (¿desconectado o modo solo carga?)"
            elif "SUBFOLDER_NOT_FOUND" in detail:
                detail = f"no se encontró la carpeta '{subfolder}' en el dispositivo"
            raise CalibreError(f"No se pudo copiar al dispositivo MTP: {detail}")

    def _ebook_convert(self) -> Path:
        if self.calibredb:
            cand = self.calibredb.parent / ("ebook-convert.exe" if os.name == "nt" else "ebook-convert")
            if cand.exists():
                return cand
        found = shutil.which("ebook-convert")
        if found:
            return Path(found)
        raise CalibreError("No se encontró ebook-convert (necesario para convertir formatos).")

    def send_to_device(
        self,
        book_id: int | None = None,
        file_path: Path | str | None = None,
        fmt: str = "",
    ) -> dict:
        self._require()
        device = self.detect_device()
        if not device:
            raise CalibreError(
                "No se detectó ningún dispositivo montado. Conecta el Kindle/Kobo por USB "
                "(modo transferencia de archivos) o define calibre.device_path / DEVICE_PATH."
            )
        fmt = (fmt or self.cfg.device_format).lower().lstrip(".")

        src: Path | None = None
        name_base = ""
        if file_path:
            src = Path(file_path)
            if not src.exists():
                raise CalibreError(f"Archivo no encontrado: {src}")
        elif book_id:
            formats = self.book_formats(book_id)
            if not formats:
                raise CalibreError(f"El libro {book_id} no tiene formatos en la biblioteca.")
            for pref in SOURCE_FORMAT_PREFERENCE:
                if pref in formats and formats[pref].exists():
                    src = formats[pref]
                    break
            if src is None:
                src = next(p for p in formats.values() if p.exists())
            title, author = self.book_title_author(book_id)
            if title:
                name_base = f"{title} - {author}" if author else title
        else:
            raise CalibreError("Indica book_id o path.")

        dest_name = f"{sanitize(name_base or src.stem)}.{fmt}"

        tmp_converted: Path | None = None
        if src.suffix.lower().lstrip(".") == fmt:
            payload = src
        else:
            tmp_converted = Path(tempfile.gettempdir()) / f"autobook_{os.getpid()}.{fmt}"
            cmd = [str(self._ebook_convert()), str(src), str(tmp_converted)]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
                creationflags=_no_window_flags(),
            )
            if result.returncode != 0 or not tmp_converted.exists():
                raise CalibreError(
                    f"ebook-convert falló (rc={result.returncode}): {(result.stderr or '')[:400]}"
                )
            payload = tmp_converted

        try:
            if device.get("interface") == "mtp":
                self._copy_to_mtp(device["name"], device.get("dest_dir") or "", payload, dest_name)
                sub = device.get("dest_dir") or ""
                dest_display = f"{device['name']}\\{sub}\\{dest_name}" if sub else f"{device['name']}\\{dest_name}"
            else:
                dest = Path(device["dest_dir"]) / dest_name
                shutil.copy2(payload, dest)
                dest_display = str(dest)
        finally:
            if tmp_converted and tmp_converted.exists():
                tmp_converted.unlink(missing_ok=True)

        return {
            "device": device["type"],
            "device_path": device["path"],
            "dest": dest_display,
            "converted_from": src.suffix.lstrip(".").upper() if payload is not src else None,
            "source": str(src),
            "note": "Expulsa el dispositivo de forma segura antes de desconectarlo.",
        }
