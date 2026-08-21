from __future__ import annotations

import atexit

from fastmcp import FastMCP

from .browser import BrowserSession
from .calibre import CalibreError, CalibreIntegration
from .calibre_mcp import CalibreMCP
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
calibre_mcp = CalibreMCP(calibre_integration)
downloader = DownloadManager(
    browser,
    config.mirrors,
    config.behavior,
    config.download_dir,
    config.files,
    calibre=calibre_integration,
)

mcp = FastMCP("autobook")


# ============================================================================
# Search & Download (existing + advanced)
# ============================================================================

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
def book_search_advanced(
    query: str = "",
    author: str = "",
    title: str = "",
    year_from: int | None = None,
    year_to: int | None = None,
    language: str | None = None,
    format: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Búsqueda avanzada combinando múltiples filtros. Construye un query para
    Anna's Archive con: author, title, year range, language, extension.
    Ejemplo: book_search_advanced(author='King', year_from=2000, year_to=2020, language='en', format='epub', limit=15)"""
    books = searcher.search_advanced(
        query=query, author=author, title=title,
        year_from=year_from, year_to=year_to,
        language=language, format=format, extension=format,
        limit=limit,
    )
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
def book_download_batch(
    books: list[dict],
    to_calibre: bool = True,
    to_device: bool = False,
    device_format: str = "",
) -> dict:
    """Cola múltiples descargas en lote. books: lista de dicts con {md5, title,
    author, extension?, series?, series_index?, language?}.
    Ejemplo: book_download_batch(books=[{"md5":"...","title":"Foo","author":"Bar"}], to_calibre=True)
    Devuelve lista de job_ids."""
    if not books:
        return {"error": "books no puede estar vacío"}
    jobs = downloader.submit_batch(
        books, to_calibre=to_calibre, to_device=to_device, device_format=device_format,
    )
    return {"jobs": [{"job_id": j.job_id, "title": j.title, "status": j.status} for j in jobs]}


@mcp.tool()
def get_download_status(job_id: str) -> dict:
    """Estado del pipeline de book_download. status: queued/downloading/importing/sending/done/waiting_captcha/error/cancelled. stage indica la etapa actual o fallida: download/calibre/device/done. Con status 'done': dest tiene el archivo, calibre_book_id el id en Calibre y device_dest la ruta en el dispositivo. Con status 'error': mira stage y los campos calibre_error/device_error para saber qué falló y reintentar solo esa etapa (calibre_add o calibre_send_to_device). Si es 'waiting_captcha', el usuario debe resolver un CAPTCHA manual en la ventana del navegador."""
    job = downloader.status(job_id)
    if job is None:
        return {"error": f"job {job_id} no encontrado"}
    return {
        "job_id": job.job_id,
        "md5": job.md5,
        "title": job.title,
        "author": job.author,
        "extension": job.extension,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "dest": job.dest,
        "error": job.error,
        "calibre_book_id": job.calibre_book_id,
        "calibre_error": job.calibre_error,
        "device_dest": job.device_dest,
        "device_error": job.device_error,
        "cancelled": job.cancelled,
    }


@mcp.tool()
def list_download_jobs(status: str | None = None, limit: int = 100) -> list[dict]:
    """Lista todos los jobs de descarga. Filtra opcionalmente por status:
    queued/downloading/importing/sending/done/waiting_captcha/error/cancelled."""
    jobs = downloader.list_jobs(status_filter=status, limit=limit)
    return [
        {
            "job_id": j.job_id,
            "title": j.title,
            "md5": j.md5,
            "status": j.status,
            "stage": j.stage,
            "progress": j.progress,
            "error": j.error,
            "cancelled": j.cancelled,
        }
        for j in jobs
    ]


@mcp.tool()
def cancel_download_job(job_id: str) -> dict:
    """Cancela un job de descarga en curso o en cola. No afecta jobs ya completados/error."""
    ok = downloader.cancel_job(job_id)
    if ok:
        return {"job_id": job_id, "cancelled": True}
    return {"job_id": job_id, "cancelled": False, "error": "job no encontrado o ya completado/error/cancelado"}


@mcp.tool()
def retry_job(job_id: str) -> dict:
    """Reintenta un job que falló o fue cancelado. Resetea el estado y lo relega
    a la cola. Útil para fallos transitorios o CAPTCHA resuelto manualmente."""
    job = downloader.retry_job(job_id)
    if job is None:
        return {"error": f"job {job_id} no encontrado o no es reintentable (debe estar en error o cancelled)"}
    return {"job_id": job.job_id, "status": job.status, "stage": job.stage}


@mcp.tool()
def retry_failed_jobs(stage: str | None = None) -> dict:
    """Reintenta todos los jobs en estado 'error'. Si stage se especifica
    (download/calibre/device), solo reintenta los del stage indicado.
    Los jobs en 'waiting_captcha' se omiten (requieren intervención manual)."""
    return downloader.retry_failed_jobs(stage=stage)


# ============================================================================
# Download helpers
# ============================================================================

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


# ============================================================================
# Calibre integration - status & basic operations
# ============================================================================

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


# ============================================================================
# Calibre Library Management (NEW)
# ============================================================================

@mcp.tool()
def calibre_search_books(
    title: str = "",
    author: str = "",
    series: str = "",
    tag: str = "",
    publisher: str = "",
    fmt: str = "",
    identifier: str = "",
    has_cover: bool | None = None,
    has_formats: bool | None = None,
    query_string: str = "",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Búsqueda avanzada en la biblioteca de Calibre. Usa filtros estructurados
    (title, author, series, tag, publisher, format, identifier) o query_string
    con sintaxis nativa de Calibre (ej: 'author:King AND tag:horror').

    Ejemplo: calibre_search_books(author='King', tag='horror', limit=20)"""
    return calibre_mcp.search_books(
        title=title, author=author, series=series, tag=tag, publisher=publisher,
        fmt=fmt, identifier=identifier, has_cover=has_cover, has_formats=has_formats,
        query_string=query_string, limit=limit, offset=offset,
    )


@mcp.tool()
def calibre_get_book_details(book_id: int) -> dict:
    """Obtiene detalles completos de un libro: título, autores, serie, tags,
    editorial, formatos, identificadores, idiomas, descripción, rating."""
    return calibre_mcp.get_book_details(book_id)


@mcp.tool()
def calibre_list_authors(
    search: str = "",
    min_books: int = 0,
    limit: int = 100,
    offset: int = 0,
    sort_by: str = "name",
) -> list[dict]:
    """Lista autores con conteo de libros. Filtra por nombre parcial y mínimo
    de libros. Sort by: 'name' (alfabético) o 'books' (más publicaciones)."""
    return calibre_mcp.list_authors(
        search=search, min_books=min_books, limit=limit, offset=offset, sort_by=sort_by,
    )


@mcp.tool()
def calibre_list_series(
    search: str = "",
    min_books: int = 0,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Lista series con conteo de libros y rango de números."""
    return calibre_mcp.list_series(search=search, min_books=min_books, limit=limit, offset=offset)


@mcp.tool()
def calibre_list_tags(
    search: str = "",
    min_books: int = 0,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Lista tags con conteo de libros."""
    return calibre_mcp.list_tags(search=search, min_books=min_books, limit=limit, offset=offset)


@mcp.tool()
def calibre_list_publishers(
    search: str = "",
    min_books: int = 0,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Lista editoriales con conteo de libros."""
    return calibre_mcp.list_publishers(search=search, min_books=min_books, limit=limit, offset=offset)


@mcp.tool()
def calibre_find_duplicates(strategy: str = "exact", limit: int = 100) -> list[list[int]]:
    """Encuentra libros duplicados en la biblioteca.
    strategy: 'exact' (misma title+author), 'isbn' (mismo ISBN), 'fuzzy' (título+autor normalizado).
    Devuelve grupos de IDs de libros duplicados."""
    return calibre_mcp.find_duplicates(strategy=strategy, limit=limit)


@mcp.tool()
def calibre_find_missing_metadata(limit: int = 100) -> dict:
    """Encuentra libros con metadata incompleta: sin portada, idioma, tags,
    formatos o editorial. Devuelve conteos y lists de book_ids por categoría."""
    return calibre_mcp.find_missing_metadata(limit=limit)


@mcp.tool()
def calibre_find_ghost_books(use_calibredb: bool = True, limit: int = 0, offset: int = 0) -> list[dict]:
    """Encuentra libros en la DB cuya carpeta o archivos no existen en disco.
    use_calibredb=True usa 'calibredb check_library' (rápido); si falla, hace
    escaneo manual. limit=0 para escanear todo (puede ser lento)."""
    return calibre_mcp.find_ghost_books(use_calibredb=use_calibredb, limit=limit, offset=offset)


@mcp.tool()
def calibre_find_orphan_files(use_calibredb: bool = True, limit: int = 100) -> list[dict]:
    """Encuentra directorios/archivos en la biblioteca sin registro en la DB."""
    return calibre_mcp.find_orphan_files(use_calibredb=use_calibredb, limit=limit)


@mcp.tool()
def calibre_library_stats() -> dict:
    """Estadísticas resumidas de la biblioteca: total de libros, autores, series,
    tags, editoriales, identificadores, formatos disponibles, libros sin portada,
    y tamaño de la base de datos."""
    return calibre_mcp.library_stats()


@mcp.tool()
def calibre_export_catalog(output_file: str = "catalog.csv", fields: str = "") -> dict:
    """Exporta el catálogo de la biblioteca a CSV, XML, EPUB o MOBI.
    fields: lista separada por comas (ej: 'title,authors,series,tags')."""
    return calibre_mcp.export_catalog(output_file=output_file, fields=fields)


@mcp.tool()
def calibre_generate_report() -> dict:
    """Genera un reporte integral de la biblioteca: estadísticas, grupos de
    duplicados, libros fantasmas, y metadata faltante."""
    return calibre_mcp.generate_report()


@mcp.tool()
def calibre_backup_database(suffix: str = "") -> dict:
    """Crea una copia de seguridad completa de metadata.db."""
    return calibre_mcp.backup_database(suffix=suffix)


@mcp.tool()
def calibre_vacuum_database(dry_run: bool = True) -> dict:
    """Compacta la base de datos después de operaciones masivas. Requiere que
    la GUI de Calibre esté cerrada. dry_run=True por defecto (solo reporta)."""
    return calibre_mcp.vacuum_database(dry_run=dry_run)


# ============================================================================
# Calibre Metadata & File Operations (NEW)
# ============================================================================

@mcp.tool()
def calibre_fetch_metadata(
    book_ids: list[int],
    source: str = "openlibrary",
    apply: bool = False,
    dry_run: bool = True,
) -> dict:
    """Obtiene metadata desde Open Library o Google Books para una lista de libros.
    source: 'openlibrary' (gratis) o 'googlebooks' (requiere cuota).
    apply=True escribe los campos encontrados (dry_run=True por defecto solo consulta).
    Si no hay ISBN, busca por título."""
    return calibre_mcp.fetch_metadata(
        book_ids=book_ids, source=source, apply=apply, dry_run=dry_run,
    )


@mcp.tool()
def calibre_embed_metadata(
    book_ids: list[int] | None = None,
    only_formats: str = "",
    dry_run: bool = True,
) -> dict:
    """Incrusta la metadata de la DB en los archivos del libro (EPUB, AZW3, etc.).
    Necesario antes de convertir/enviar al dispositivo para que vea metadata corregida.
    Si book_ids es None, procesa TODOS los libros. dry_run=True por defecto."""
    return calibre_mcp.embed_metadata(
        book_ids=book_ids, only_formats=only_formats, dry_run=dry_run,
    )


@mcp.tool()
def calibre_verify_file_integrity(book_ids: list[int] | None = None) -> dict:
    """Verifica que todos los archivos de formato referenciados en la DB existan
    en disco. Si book_ids es None, verifica todos."""
    return calibre_mcp.verify_file_integrity(book_ids=book_ids)


@mcp.tool()
def calibre_bulk_set_metadata(updates: list[dict], dry_run: bool = True) -> dict:
    """Aplica cambios de metadata a múltiples libros en una sola llamada.
    updates: [{book_id, fields: {title, authors, series, tags, ...}}, ...]
    dry_run=True por defecto (solo reporta qué haría)."""
    return calibre_mcp.bulk_set_metadata(updates=updates, dry_run=dry_run)


# ============================================================================
# Calibre Cleanup & Maintenance (NEW)
# ============================================================================

@mcp.tool()
def calibre_cleanup_orphan_links(dry_run: bool = True) -> dict:
    """Elimina entradas huérfano en tablas de enlace (link tables) donde el
    book_id ya no existe. Requiere Calibre cerrado para dry_run=False."""
    return calibre_mcp.cleanup_orphan_links(dry_run=dry_run)


@mcp.tool()
def calibre_find_orphan_links() -> list[dict]:
    """Encuentra entradas huérfano en tablas de enlace (author, tag, series, etc.)
    donde el book_id ya no existe en la tabla books."""
    return calibre_mcp.find_orphan_links(dry_run=True)


@mcp.tool()
def calibre_fix_author_sort(limit: int = 100, dry_run: bool = True) -> dict:
    """Sincroniza books.author_sort con los campos sort de los autores vinculados.
    dry_run=True por defecto."""
    return calibre_mcp.fix_author_sort(limit=limit, dry_run=dry_run)


@mcp.tool()
def calibre_fix_book_paths(book_ids: list[int] | None = None, dry_run: bool = True) -> dict:
    """Renombra directorios en disco para que coincidan con author/title en la DB.
    Si book_ids es None, revisa todos. dry_run=True por defecto."""
    return calibre_mcp.fix_book_paths(book_ids=book_ids, dry_run=dry_run)


@mcp.tool()
def calibre_fix_series_numbers(series_id: int, assignments: list[dict], dry_run: bool = True) -> dict:
    """Corrige numeración de una serie asignando índices específicos a libros.
    assignments: [{book_id, index}, ...]
    dry_run=True por defecto."""
    return calibre_mcp.fix_series_numbers(series_id=series_id, assignments=assignments, dry_run=dry_run)


@mcp.tool()
def calibre_rename_author(author_id: int, new_name: str, new_sort: str = "", dry_run: bool = True) -> dict:
    """Renombra un autor directamente en la DB. Soporta renames de solo mayúsculas/minúsculas
    (ej: BOECIO → Boecio). dry_run=True por defecto."""
    return calibre_mcp.rename_author(author_id=author_id, new_name=new_name, new_sort=new_sort, dry_run=dry_run)


@mcp.tool()
def calibre_merge_authors(canonical_id: int, variant_ids: list[int], dry_run: bool = True) -> dict:
    """Une variantes de autor (casos, iniciales, acentos) al autor canónico.
    dry_run=True por defecto."""
    return calibre_mcp.merge_authors(canonical_id=canonical_id, variant_ids=variant_ids, dry_run=dry_run)


@mcp.tool()
def calibre_find_author_variants(limit: int = 100) -> list[dict]:
    """Encuentra grupos de autores que parecen ser la misma persona
    (casos, iniciales, acentos). Requiere revisión manual antes de merge."""
    return calibre_mcp.find_author_variants(limit=limit)


@mcp.tool()
def calibre_normalize_uppercase(item_type: str = "all", limit: int = 100, dry_run: bool = True) -> dict:
    """Convierte TÍTULOS/TAGS/PUBLISHERS/SERIES en MAYÚSCULAS a Title Case.
    item_type: 'titles', 'tags', 'publishers', 'series', o 'all'.
    dry_run=True por defecto."""
    return calibre_mcp.normalize_uppercase(item_type=item_type, limit=limit, dry_run=dry_run)


@mcp.tool()
def calibre_find_compilation_coverage(author_id: int, min_compilation_kb: int = 200) -> dict:
    """Detecta qué obras individuales de un autor están cubiertas por sus
    EPUB de recopilación. Usa TOC extraction (limitado)."""
    return calibre_mcp.find_compilation_coverage(author_id=author_id, min_compilation_kb=min_compilation_kb)


@mcp.tool()
def calibre_analyze_author(author_id: int) -> dict:
    """Análisis completo de un autor: variantes, duplicados, gaps en series,
    metadata faltante. Punto de partida para limpieza de autor."""
    return calibre_mcp.analyze_author(author_id=author_id)


@mcp.tool()
def calibre_suggest_dedup_resolution(book_ids: list[int]) -> dict:
    """Dada un grupo de libros duplicados, sugiere cuál conservar usando
    un score de calidad: formato (EPUB>FB2>MOBI>PDF>...) → tiene portada → tiene comentarios → ISBN → ID."""
    return calibre_mcp.suggest_dedup_resolution(book_ids=book_ids)


# ============================================================================
# Calibre Full-Text Search (NEW)
# ============================================================================

@mcp.tool()
def calibre_fts_index(action: str = "status") -> dict:
    """Gestiona el índice de búsqueda full-text: status, enable, disable, reindex."""
    return calibre_mcp.fts_index(action=action)


@mcp.tool()
def calibre_fts_search(query: str, limit: int = 50) -> list[dict]:
    """Búsqueda full-text dentro del contenido de los libros."""
    return calibre_mcp.fts_search(query=query, limit=limit)


# ============================================================================
# Device Management (NEW)
# ============================================================================

@mcp.tool()
def calibre_list_devices() -> list[dict]:
    """Lista todos los dispositivos Kindle/Kobo detectados (USB + MTP)."""
    return calibre_mcp.list_devices()


@mcp.tool()
def calibre_eject_device(device_name: str | None = None, drive_letter: str | None = None) -> dict:
    """Expulsa de forma segura un dispositivo conectado (Kindle/Kobo) vía PowerShell.
    Usa device_name (para MTP) o drive_letter (para USB, ej: 'E:')."""
    return calibre_mcp.eject_device(device_name=device_name, drive_letter=drive_letter)


if __name__ == "__main__":
    mcp.run()