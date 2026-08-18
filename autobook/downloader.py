from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from .browser import BrowserSession, NeedsCaptchaError
from .config import BehaviorConfig, FileConfig
from .organize import build_destination


@dataclass
class DownloadJob:
    job_id: str
    md5: str
    title: str
    author: str
    extension: str
    series: str | None = None
    series_index: int | float | None = None
    status: str = "queued"
    progress: float = 0.0
    dest: str | None = None
    error: str | None = None


class DownloadManager:
    def __init__(
        self,
        browser: BrowserSession,
        mirrors: list[str],
        behavior_cfg: BehaviorConfig,
        download_dir: Path,
        file_cfg: FileConfig,
    ) -> None:
        self._browser = browser
        self._mirrors = list(mirrors)
        self._behavior_cfg = behavior_cfg
        self._download_dir = download_dir
        self._file_cfg = file_cfg
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
    ) -> DownloadJob:
        job = DownloadJob(
            job_id=uuid.uuid4().hex[:10],
            md5=md5,
            title=title,
            author=author,
            extension=extension,
            series=series,
            series_index=series_index,
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
                self._set(job, status="error", error=" | ".join(errors))

    def _run_with_mirror(self, mirror: str, job: DownloadJob) -> None:
        self._set(job, status="downloading", progress=0.05)
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
            job.author,
            job.extension,
            overwrite=self._file_cfg.overwrite,
            series=job.series,
            series_index=job.series_index,
        )
        self._set(job, progress=0.3)

        self._browser.run_download(href, str(dest), timeout_ms=self._browser._cfg.timeout_ms)
        self._set(job, status="done", progress=1.0, dest=str(dest))