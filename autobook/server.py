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
    """Busca libros en Anna's Archive. language es código ISO-639-1 (es, en, fr...) y format es epub/pdf/mobi/azw3. Devuelve resultados con title, author, language, extension, filesize, year, md5 y url. Usa el md5 del resultado para book_download. IMPORTANTE al elegir resultado: prefiere títulos con mayúsculas correctas, autores limpios (idealmente 'Apellido, Nombre') y tamaño razonable (descarta los de pocos bytes); los resultados con metadatos sucios (corchetes, minúsculas, contribuyentes extra) ensucian el nombre final en Calibre y el dispositivo."""
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
    language: str = "",
    to_calibre: bool = True,
    to_device: bool = False,
    device_format: str = "",
) -> dict:
    """Pipeline completo: descarga un libro por su md5 (ver book_search), luego (si to_calibre) lo importa a la biblioteca de Calibre con metadatos limpios y sin duplicados, y luego (si to_device) lo convierte y envía al Kindle/Kobo conectado. Valida ANTES de empezar: si to_calibre/to_device es true y falta Calibre o el dispositivo, devuelve error de inmediato. Parámetros: series/series_index para nombrar volúmenes coherentemente; language (ISO-639-1) para el metadato de idioma; device_format opcional (por defecto calibre.device_format, azw3). Devuelve job_id; monitorea con get_download_status. Si una etapa posterior a la descarga falla, reintenta esa etapa con calibre_add(job_id) o calibre_send_to_device(book_id)."""
    try:
        job = downloader.submit(
            md5, title, author, extension, series, series_index,
            language=language, to_calibre=to_calibre, to_device=to_device,
            device_format=device_format,
        )
    except ValueError as exc:
        return {"error": str(exc)}
    return {"job_id": job.job_id, "status": job.status}


@mcp.tool()
def get_download_status(job_id: str) -> dict:
    """Estado del pipeline de book_download. status: queued/downloading/importing/sending/done/waiting_captcha/error. stage indica la etapa actual o fallida: download/calibre/device/done. Con status 'done': dest tiene el archivo, calibre_book_id el id en Calibre y device_dest la ruta en el dispositivo. Con status 'error': mira stage y los campos calibre_error/device_error para saber qué falló y reintentar solo esa etapa (calibre_add o calibre_send_to_device). Si es 'waiting_captcha', el usuario debe resolver un CAPTCHA manual en la ventana del navegador."""
    job = downloader.status(job_id)
    if job is None:
        return {"error": f"job {job_id} no encontrado"}
    return {
        "job_id": job.job_id,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "dest": job.dest,
        "error": job.error,
        "calibre_book_id": job.calibre_book_id,
        "calibre_error": job.calibre_error,
        "device_dest": job.device_dest,
        "device_error": job.device_error,
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
    """Estado de la integración con Calibre: si calibredb está encontrado, ruta de la biblioteca, si la GUI de Calibre está abierta (puede bloquear escrituras) y dispositivo detectado (Kindle/Kobo, por unidad o MTP). Úsala para comprobar que todo está listo antes de un book_download con to_calibre/to_device."""
    return calibre_integration.status()


@mcp.tool()
def calibre_add(
    job_id: str = "",
    path: str = "",
    title: str = "",
    author: str = "",
    language: str = "",
) -> dict:
    """Importa un libro a la biblioteca de Calibre con metadatos limpios (título, autor normalizado, idioma, serie, número de serie e identificador annas:<md5>) y sin crear duplicados. Es la forma de reintentar la etapa Calibre de un book_download que falló en stage=calibre: pasa su job_id. También acepta path de un archivo local (con title/author/language opcionales). Devuelve book_id y duplicated."""
    job = None
    if job_id:
        job = downloader.status(job_id)
        if job is None:
            return {"error": f"job {job_id} no encontrado"}
        if not job.dest:
            return {"error": f"job {job_id} aún no tiene archivo descargado (status={job.status})"}
        file_path = job.dest
    elif path:
        file_path = path
    else:
        return {"error": "Indica job_id (de book_download) o path de un archivo."}

    from .organize import compute_author_sort, compute_title_sort, normalize_author

    raw_author = author or (job.author if job else "")
    clean_author = normalize_author(raw_author)
    clean_title = title or (job.title if job else "")
    lang = language or (job.language if job else "")
    try:
        result = calibre_integration.add_book(
            file_path,
            title=clean_title,
            author=clean_author,
            language=lang,
            series=job.series if job else None,
            series_index=job.series_index if job else None,
            identifier_md5=job.md5 if job else "",
        )
        book_id = result.get("book_id")
        if book_id and not result.get("duplicated"):
            calibre_integration.set_metadata(
                book_id,
                {
                    "title": clean_title,
                    "title_sort": compute_title_sort(clean_title, lang),
                    "authors": clean_author,
                    "author_sort": compute_author_sort(clean_author),
                },
            )
        return result
    except CalibreError as exc:
        return {"error": str(exc)}


@mcp.tool()
def calibre_send_to_device(book_id: int = 0, path: str = "", format: str = "") -> dict:
    """Envía un libro al dispositivo conectado (Kindle/Kobo, por unidad o MTP; hay que asegurarse de que esté conectado en modo transferencia). Por book_id de la biblioteca de Calibre (devuelto por calibre_add) o por path de un archivo local. Incrusta los metadatos corregidos y convierte al formato destino si hace falta (format opcional; por defecto calibre.device_format, azw3). Es la forma de reintentar la etapa dispositivo de un book_download que falló en stage=device. Devuelve la ruta en el dispositivo."""
    try:
        if book_id:
            calibre_integration.embed_metadata(book_id, "epub")
        return calibre_integration.send_to_device(
            book_id=book_id or None,
            file_path=path or None,
            fmt=format,
        )
    except CalibreError as exc:
        return {"error": str(exc)}


if __name__ == "__main__":
    mcp.run()