from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from .browser import BrowserSession, NeedsCaptchaError
from .config import BehaviorConfig, FileConfig
from .organize import build_destination, compute_author_sort, compute_title_sort, normalize_author


@dataclass
class DownloadJob:
    job_id: str
    md5: str
    title: str
    author: str
    extension: str
    series: str | None = None
    series_index: int | float | None = None
    language: str = ""
    to_calibre: bool = False
    to_device: bool = False
    device_format: str = ""
    status: str = "queued"
    stage: str = "download"
    progress: float = 0.0
    dest: str | None = None
    error: str | None = None
    calibre_book_id: int | None = None
    calibre_error: str | None = None
    device_dest: str | None = None
    device_error: str | None = None


class DownloadManager:
    def __init__(
        self,
        browser: BrowserSession,
        mirrors: list[str],
        behavior_cfg: BehaviorConfig,
        download_dir: Path,
        file_cfg: FileConfig,
        calibre=None,
    ) -> None:
        self._browser = browser
        self._mirrors = list(mirrors)
        self._behavior_cfg = behavior_cfg
        self._download_dir = download_dir
        self._file_cfg = file_cfg
        self._calibre = calibre
        self._jobs: dict[str, DownloadJob] = {}
        self._lock = threading.Lock()

    def submit(
        self,
        md5: str,
        title: str,
        author: str,
        extension: str,
        series: str | None = None,
        series_index: int | float | None = None,
        language: str = "",
        to_calibre: bool = False,
        to_device: bool = False,
        device_format: str = "",
    ) -> DownloadJob:
        """Valida los destinos pedidos (fail-fast) y lanza el pipeline completo:
        descarga -> Calibre -> dispositivo. Lanza ValueError si falta algo."""
        if to_calibre or to_device:
            if self._calibre is None or not self._calibre.available():
                raise ValueError(
                    "Calibre no detectado (calibredb o biblioteca). Instala Calibre, "
                    "define calibre.library_path/CALIBRE_LIBRARY, o usa to_calibre=false y to_device=false."
                )
        if to_device:
            if self._calibre.detect_device() is None:
                raise ValueError(
                    "No se detectó ningún dispositivo (Kindle/Kobo). Conéctalo por USB "
                    "(modo transferencia) y reintenta, o usa to_device=false."
                )
        job = DownloadJob(
            job_id=uuid.uuid4().hex[:10],
            md5=md5,
            title=title,
            author=author,
            extension=extension,
            series=series,
            series_index=series_index,
            language=language,
            to_calibre=to_calibre,
            to_device=to_device,
            device_format=device_format,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def status(self, job_id: str) -> DownloadJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _set(self, job: DownloadJob, **kwargs) -> None:
        with self._lock:
            for k, v in kwargs.items():
                setattr(job, k, v)

    def _run(self, job: DownloadJob) -> None:
        errors: list[str] = []
        for mirror in self._mirrors:
            try:
                self._run_with_mirror(mirror, job)
                return
            except NeedsCaptchaError as exc:
                self._set(job, status="waiting_captcha", error=str(exc))
                return
            except Exception as exc:
                errors.append(f"{mirror}: {exc}")
                self._set(job, status="error", stage="download", error=" | ".join(errors))

    def _run_with_mirror(self, mirror: str, job: DownloadJob) -> None:
        self._set(job, status="downloading", stage="download", progress=0.05)
        href = self._browser.get_slow_download_href(
            f"{mirror}/md5/{job.md5}",
            challenge_timeout_s=self._behavior_cfg.challenge_timeout_s,
        )
        if not href:
            raise RuntimeError("enlace slow_download no encontrado en la página del md5")
        if not href.startswith("http"):
            href = mirror + href

        dest = build_destination(
            self._download_dir,
            job.title,
            normalize_author(job.author),
            job.extension,
            overwrite=self._file_cfg.overwrite,
            series=job.series,
            series_index=job.series_index,
        )
        self._set(job, progress=0.3)

        self._browser.run_download(href, str(dest), timeout_ms=self._browser._cfg.timeout_ms)
        self._set(job, dest=str(dest), progress=1.0)
        self._pipeline(job)

    def _pipeline(self, job: DownloadJob) -> None:
        """Etapas posteriores a la descarga: Calibre y/o dispositivo."""
        if job.to_calibre:
            self._set(job, status="importing", stage="calibre")
            try:
                author = normalize_author(job.author)
                result = self._calibre.add_book(
                    job.dest,
                    title=job.title,
                    author=author,
                    language=job.language,
                    series=job.series,
                    series_index=job.series_index,
                    identifier_md5=job.md5,
                )
                book_id = result.get("book_id")
                self._set(job, calibre_book_id=book_id)
                if book_id and not result.get("duplicated"):
                    # calibredb no recalcula los sort: se fijan explícitamente.
                    self._calibre.set_metadata(
                        book_id,
                        {
                            "title": job.title,
                            "title_sort": compute_title_sort(job.title, job.language),
                            "authors": author,
                            "author_sort": compute_author_sort(author),
                        },
                    )
            except Exception as exc:
                self._set(job, status="error", stage="calibre",
                          calibre_error=str(exc), error=f"calibre: {exc}")
                return
        if job.to_device:
            self._set(job, status="sending", stage="device")
            try:
                if job.calibre_book_id:
                    self._calibre.embed_metadata(job.calibre_book_id, "epub")
                    result = self._calibre.send_to_device(
                        book_id=job.calibre_book_id, fmt=job.device_format
                    )
                else:
                    result = self._calibre.send_to_device(
                        file_path=job.dest, fmt=job.device_format
                    )
                self._set(job, device_dest=result.get("dest"))
            except Exception as exc:
                self._set(job, status="error", stage="device",
                          device_error=str(exc), error=f"dispositivo: {exc}")
                return
        self._set(job, status="done", stage="done")
