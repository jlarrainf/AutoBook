from __future__ import annotations

import asyncio
import subprocess
import threading
import time
from pathlib import Path

from playwright.async_api import async_playwright

from .config import BrowserConfig

DDG_TITLE = "DDoS-Guard"
SLOW_DOWNLOAD_SELECTOR = "a[href*='/slow_download/']"

CHROME_CANDIDATES = [
    Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
    Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
]
EDGE_CANDIDATES = [
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
]


class NeedsCaptchaError(RuntimeError):
    pass


class BrowserSession:
    """Conduce un navegador Chromium real (Chrome/Edge) vía CDP.

    El navegador se lanza como un proceso normal con un PERFIL PROPIO y se
    conecta por Playwright. Se usa a propósito un navegador real con ventana:
    DDoS-Guard se autoverifica y no pide captcha.

    IMPORTANTE: close() NUNCA mata el proceso del navegador. El usuario puede
    tener su Edge/Chrome abierto con la misma instancia y un kill cerraría sus
    pestañas. Solo se cierra la conexión Playwright; el navegador queda vivo.
    """

    def __init__(self, cfg: BrowserConfig) -> None:
        self._cfg = cfg
        self._proc: subprocess.Popen | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._loop_ready = threading.Event()
        self._pw = None
        self._context = None

    @property
    def headless(self) -> bool:
        return self._cfg.headless

    @property
    def alive(self) -> bool:
        return self._context is not None

    def _browser_path(self) -> str:
        if self._cfg.binary:
            p = Path(self._cfg.binary)
            if p.exists():
                return str(p)
            raise RuntimeError(f"Binario de navegador no encontrado: {self._cfg.binary}")
        for p in CHROME_CANDIDATES + EDGE_CANDIDATES:
            if p.exists():
                return str(p)
        raise RuntimeError("No se encontró Chrome ni Edge. Instala uno o define browser.binary en config.yaml.")

    @staticmethod
    def _port_up(port: int) -> bool:
        import socket

        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            return False

    def _wait_port(self, port: int, timeout_s: float = 30) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._port_up(port):
                return
            time.sleep(0.5)
        raise RuntimeError(f"El navegador no expuso el puerto de depuración {port}")

    # -- event loop --

    def _run_on_loop(self, coro):
        if self._loop is None:
            raise RuntimeError("BrowserSession no iniciada. Llama a start() antes.")
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def _loop_main(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop_ready.set()
        self._loop.run_forever()

    def _ensure_loop(self) -> None:
        if self._loop is None:
            self._loop_ready = threading.Event()
            self._loop_thread = threading.Thread(target=self._loop_main, daemon=True)
            self._loop_thread.start()
            self._loop_ready.wait(10)

    def start(self) -> None:
        if self._context is not None:
            return
        if not self._port_up(self._cfg.cdp_port):
            profile = Path(self._cfg.user_data_dir).resolve()
            profile.mkdir(parents=True, exist_ok=True)
            self._proc = subprocess.Popen(
                [
                    self._browser_path(),
                    f"--remote-debugging-port={self._cfg.cdp_port}",
                    f"--user-data-dir={profile}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "about:blank",
                ]
            )
            self._wait_port(self._cfg.cdp_port)
        else:
            self._proc = None
        self._ensure_loop()
        self._run_on_loop(self._connect())

    async def _connect(self) -> None:
        self._pw = await async_playwright().start()
        browser = await self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{self._cfg.cdp_port}")
        self._context = browser.contexts[0]

    def _drop_connection(self) -> None:
        if self._pw is not None and self._loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(self._pw.stop(), self._loop).result(5)
            except Exception:
                pass
        self._pw = None
        self._context = None

    def _ensure_started(self) -> None:
        if self._context is None:
            self.start()
            return
        try:
            self._run_on_loop(self._healthy())
        except Exception:
            self._drop_connection()
            self.start()

    async def _healthy(self) -> bool:
        await self._context.pages()
        return True

    # -- high level operations (thread-safe, blocking) --

    def goto_html(self, url: str, *, wait_selector: str | None = None, challenge_timeout_s: float = 120.0) -> str:
        self._ensure_started()
        return self._run_on_loop(self._goto_html(url, wait_selector, challenge_timeout_s))

    async def _wait_ready(self, page, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                title = (await page.title()) or ""
            except Exception:
                return
            if title.startswith(DDG_TITLE) or title.startswith("Loading"):
                await page.wait_for_timeout(2000)
                continue
            return
        try:
            title = (await page.title()) or ""
        except Exception:
            return
        if title.startswith(DDG_TITLE):
            raise NeedsCaptchaError(
                "El challenge de DDoS-Guard no se resolvió automáticamente. "
                "Revisa la ventana del navegador abierta y resuelve el captcha manual si aparece."
            )

    async def _goto_html(self, url: str, wait_selector: str | None, timeout_s: float) -> str:
        page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await self._wait_ready(page, timeout_s)
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=30000)
                except Exception:
                    pass
            return await page.content()
        finally:
            await page.close()

    def get_slow_download_href(self, md5_url: str, challenge_timeout_s: float = 120.0) -> tuple[str, str]:
        """Devuelve (href de slow_download, url de la portada) de la página del md5."""
        self._ensure_started()
        return self._run_on_loop(self._get_slow_download_href(md5_url, challenge_timeout_s))

    async def _get_slow_download_href(self, md5_url: str, timeout_s: float) -> tuple[str, str]:
        page = await self._context.new_page()
        try:
            await page.goto(md5_url, wait_until="domcontentloaded", timeout=60000)
            await self._wait_ready(page, timeout_s)
            cover_url = ""
            try:
                cover_url = await page.evaluate(
                    "() => {"
                    "const m = document.querySelector('meta[property=\"og:image\"]');"
                    "if (m && m.content) return m.content;"
                    "const img = document.querySelector('img.md5-cover, img[class*=\"cover\"]');"
                    "return img ? (img.currentSrc || img.src) : '';"
                    "}"
                ) or ""
            except Exception:
                pass
            loc = page.locator(SLOW_DOWNLOAD_SELECTOR).first
            try:
                await loc.wait_for(timeout=30000)
            except Exception:
                return "", cover_url
            href = await loc.get_attribute("href")
            return href or "", cover_url
        finally:
            await page.close()

    def run_download(self, href: str, dest: str, timeout_ms: int = 600000) -> None:
        self._ensure_started()
        self._run_on_loop(self._run_download(href, dest, timeout_ms))

    async def _run_download(self, href: str, dest: str, timeout_ms: int) -> None:
        page = await self._context.new_page()
        try:
            await page.goto(href, wait_until="domcontentloaded", timeout=60000)
            start = page.locator("a:has-text('Download now'), a:has-text('Download with short filename')").first
            try:
                await start.wait_for(state="visible", timeout=30000)
            except Exception:
                pass
            async with page.expect_download(timeout=timeout_ms) as dl_info:
                await start.click(timeout=30000)
                await page.wait_for_timeout(3000)
            download = await dl_info.value
            await download.save_as(str(dest))
        finally:
            await page.close()

    def close(self) -> None:
        """Cierra la conexión Playwright pero NUNCA mata el proceso del navegador
        (evita cerrar las pestañas de la sesión normal del usuario)."""
        self._drop_connection()
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass
            self._loop_thread.join(timeout=5)
        self._loop = None
        self._loop_thread = None
        self._proc = None