from __future__ import annotations

import atexit

from fastmcp import FastMCP

from .browser import BrowserSession
from .calibre import CalibreError, CalibreIntegration
from .config import Config
from .downloader import DownloadManager
from .mirrors import MirrorManager
from .search import Searcher

config = Config.load()
mirrors = MirrorManager(config.mirrors)
browser = BrowserSession(config.browser)
atexit.register(browser.close)
searcher = Searcher(
    mirrors,
    browser,
    config.behavior.request_delay_min,
    config.behavior.request_delay_max,
    config.behavior.challenge_timeout_s,
)
calibre_integration = CalibreIntegration(config.calibre)
downloader = DownloadManager(
    browser,
    config.mirrors,
    config.behavior,
    config.download_dir,
    config.files,
    calibre=calibre_integration,
)

mcp = FastMCP("autobook")


@mcp.tool()
def book_search(
    query: str,
    language: str | None = None,
    format: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Busca libros en Anna's Archive. language es código ISO-639-1 (es, en, fr...) y format es epub/pdf/mobi/azw3. Devuelve resultados con title, author, language, extension, filesize, year, md5 y url. Usa el md5 del resultado para book_download."""
    language = language or config.default_language
    format = format or config.default_format
    books = searcher.search(query, language=language, extension=format, limit=limit)
    return [b.__dict__ for b in books]


@mcp.tool()
def book_download(
    md5: str,
    title: str,
    author: str = "",
    extension: str = "epub",
    series: str | None = None,
    series_index: int | float | None = None,
) -> dict:
    """Inicia la descarga de un libro por su md5 (ver book_search). Por defecto se guarda en <DOWNLOAD_DIR>/<Autor>/<Título>.<ext>. Si indicas series (y opcionalmente series_index) se guarda en <DOWNLOAD_DIR>/<Serie>/Book <NN> - <Título>.<ext>, con nombres coherentes para todos los volúmenes de una misma serie descargados juntos."""
    job = downloader.submit(md5, title, author, extension, series, series_index)
    return {"job_id": job.job_id, "status": job.status}


@mcp.tool()
def get_download_status(job_id: str) -> dict:
    """Devuelve el estado de una descarga iniciada con book_download. status puede ser queued/downloading/waiting_captcha/done/error. Cuando sea 'done', lee el campo dest. Si es 'waiting_captcha', el usuario debe resolver un CAPTCHA manual en la ventana del navegador."""
    job = downloader.status(job_id)
    if job is None:
        return {"error": f"job {job_id} no encontrado"}
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "dest": job.dest,
        "error": job.error,
        "cover": job.cover,
        "calibre_book_id": job.calibre_book_id,
        "calibre_error": job.calibre_error,
    }


@mcp.tool()
def set_download_dir(path: str) -> str:
    """Cambia la carpeta de descargas en caliente (no requiere reiniciar)."""
    global config
    from pathlib import Path

    config.download_dir = Path(path).resolve()
    downloader._download_dir = config.download_dir
    return str(config.download_dir)


@mcp.tool()
def check_mirrors() -> dict:
    """Comprueba qué mirrors de Anna's Archive responden y devuelve el principal en uso."""
    alive = {m: mirrors.healthy(m) for m in config.mirrors}
    return {"mirrors": alive, "primary": mirrors.primary}


@mcp.tool()
def session_info() -> dict:
    """Devuelve el estado de la sesión de navegador (ventana de Chrome vía CDP) y la carpeta de descargas."""
    return {
        "headless": browser.headless,
        "browser_alive": browser.alive,
        "download_dir": str(config.download_dir),
        "mirror": mirrors.primary,
    }


@mcp.tool()
def calibre_status() -> dict:
    """Estado de la integración con Calibre: si calibredb está encontrado, ruta de la biblioteca, si la GUI de Calibre está abierta (puede bloquear escrituras), auto_import y dispositivo montado (Kindle/Kobo)."""
    return calibre_integration.status()


@mcp.tool()
def calibre_add(
    job_id: str = "",
    path: str = "",
    title: str = "",
    author: str = "",
    language: str = "",
) -> dict:
    """Importa un libro a la biblioteca de Calibre y fija sus metadatos básicos (título, autor, idioma, serie, número de serie, identificador annas:<md5> y portada si se capturó). Usa job_id de un book_download terminado, o path de un archivo local (con title/author/language opcionales si no hay job). Devuelve book_id y si ya existía (duplicated). Requiere Calibre instalado."""
    job = None
    if job_id:
        job = downloader.status(job_id)
        if job is None:
            return {"error": f"job {job_id} no encontrado"}
        if job.status != "done" or not job.dest:
            return {"error": f"job {job_id} aún no terminó (status={job.status})"}
        file_path = job.dest
    elif path:
        file_path = path
    else:
        return {"error": "Indica job_id (de book_download) o path de un archivo."}

    try:
        result = calibre_integration.add_book(
            file_path,
            title=title or (job.title if job else ""),
            author=author or (job.author if job else ""),
            language=language,
            series=job.series if job else None,
            series_index=job.series_index if job else None,
            identifier_md5=job.md5 if job else "",
            cover_path=job.cover if job else None,
        )
        return result
    except CalibreError as exc:
        return {"error": str(exc)}


@mcp.tool()
def calibre_send_to_device(book_id: int = 0, path: str = "", format: str = "") -> dict:
    """Envía un libro al dispositivo conectado (Kindle/Kobo). Por book_id de la biblioteca de Calibre (devuelto por calibre_add) o por path de un archivo local. Convierte al formato destino si hace falta (format opcional; por defecto calibre.device_format, mobi). Devuelve la ruta en el dispositivo. El dispositivo debe estar montado (modo transferencia)."""
    try:
        return calibre_integration.send_to_device(
            book_id=book_id or None,
            file_path=path or None,
            fmt=format,
        )
    except CalibreError as exc:
        return {"error": str(exc)}


if __name__ == "__main__":
    mcp.run()