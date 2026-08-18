from __future__ import annotations

from curl_cffi import requests as cffi_requests


class MirrorManager:
    def __init__(self, mirrors: list[str]) -> None:
        self._mirrors = list(mirrors)
        self._index = 0

    @property
    def primary(self) -> str:
        return self._mirrors[self._index % len(self._mirrors)]

    def healthy(self, mirror: str, timeout: float = 8.0) -> bool:
        try:
            resp = cffi_requests.get(
                f"{mirror}/",
                timeout=timeout,
                impersonate="chrome",
                allow_redirects=True,
            )
            return resp.status_code < 400
        except Exception:
            return False

    def probe(self) -> str:
        for i, mirror in enumerate(self._mirrors):
            if self.healthy(mirror):
                self._index = i
                return mirror
        raise RuntimeError("Ningún mirror de Anna's Archive responde")

    def next(self) -> str:
        self._index = (self._index + 1) % len(self._mirrors)
        return self.primary