from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from .browser import BrowserSession
from .mirrors import MirrorManager

LANG_RE = re.compile(r"\[([a-z]{2,3})\]")
EXT_RE = re.compile(r"\b(epub|pdf|mobi|azw3|djvu|fb2|cbz|cbr)\b", re.IGNORECASE)
SIZE_RE = re.compile(r"([0-9][0-9.,]*\s?[KMGT]?i?B)")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

RESULT_SELECTOR = "div.js-aarecord-list-outer"
ROW_CLASS = "border-b"


@dataclass
class Book:
    title: str
    author: str
    language: str
    extension: str
    filesize: str
    year: str
    md5: str
    url: str


class Searcher:
    def __init__(
        self,
        mirrors: MirrorManager,
        browser: BrowserSession,
        delay_min: float = 2.0,
        delay_max: float = 6.0,
        challenge_timeout_s: float = 180.0,
    ) -> None:
        self._mirrors = mirrors
        self._browser = browser
        self._delay_min = delay_min
        self._delay_max = delay_max
        self._challenge_timeout_s = challenge_timeout_s

    def _sleep(self) -> None:
        time.sleep(random.uniform(self._delay_min, self._delay_max))

    def search(
        self,
        query: str,
        language: str | None = None,
        extension: str | None = None,
        limit: int = 10,
    ) -> list[Book]:
        base = self._mirrors.primary
        params: dict[str, str] = {"q": query}
        if language:
            params["lang"] = language
        if extension:
            params["ext"] = extension

        self._sleep()
        try:
            resp = cffi_requests.get(
                f"{base}/search",
                params=params,
                impersonate="chrome",
                timeout=8,
                allow_redirects=True,
            )
            if resp.status_code < 400:
                return self._parse(resp.text, base, limit)
        except Exception:
            pass

        return self._search_via_browser(base, params, limit)

    def build_advanced_query(
        self,
        query: str = "",
        author: str = "",
        title: str = "",
        year_from: int | None = None,
        year_to: int | None = None,
        language: str | None = None,
        format: str | None = None,
        extension: str | None = None,
        limit: int = 20,
    ) -> str:
        """Construye un query string para Anna's Archive combinando múltiples filtros.
        Sintaxis: author:Foo title:Bar year:2010..2020 lang:es ext:epub"""
        parts: list[str] = []
        if query:
            parts.append(query)
        if author:
            parts.append(f"author:{author}")
        if title:
            parts.append(f"title:{title}")
        if year_from is not None or year_to is not None:
            yf = str(year_from) if year_from is not None else ""
            yt = str(year_to) if year_to is not None else ""
            parts.append(f"year:{yf}..{yt}")
        if language:
            parts.append(f"lang:{language}")
        ext = extension or format
        if ext:
            parts.append(f"ext:{ext}")
        return " ".join(parts)

    def search_advanced(
        self,
        query: str = "",
        author: str = "",
        title: str = "",
        year_from: int | None = None,
        year_to: int | None = None,
        language: str | None = None,
        format: str | None = None,
        extension: str | None = None,
        limit: int = 20,
    ) -> list[Book]:
        """Búsqueda avanzada combinando múltiples filtros."""
        q = self.build_advanced_query(
            query=query, author=author, title=title,
            year_from=year_from, year_to=year_to,
            language=language, format=format, extension=extension,
        )
        return self.search(q, language=language, extension=format or extension, limit=limit)

    def _search_via_browser(self, base: str, params: dict[str, str], limit: int) -> list[Book]:
        url = f"{base}/search?{urlencode(params)}"
        html = self._browser.goto_html(
            url,
            wait_selector=RESULT_SELECTOR,
            challenge_timeout_s=self._challenge_timeout_s,
        )
        return self._parse(html, base, limit)

    def _parse(self, html: str, base: str, limit: int) -> list[Book]:
        soup = BeautifulSoup(html, "lxml")
        container = soup.select_one(RESULT_SELECTOR)
        if container is None:
            return []

        books: list[Book] = []
        for row in container.find_all("div", recursive=False):
            classes = " ".join(row.get("class", []))
            if ROW_CLASS not in classes:
                continue
            book = self._parse_row(row, base)
            if book is not None:
                books.append(book)
                if len(books) >= limit:
                    break
        return books

    def _parse_row(self, row, base: str) -> Book | None:
        md5 = ""
        title = ""
        for a in row.select("a[href*='/md5/']"):
            md5 = a.get("href", "").split("/md5/")[-1].strip("/")
            text = a.get_text(" ", strip=True)
            if text:
                title = text
                break
        if not md5 or not title:
            return None

        text = row.get_text(" ", strip=True)
        return Book(
            title=title,
            author=self._extract_author(row),
            language=self._extract_language(text),
            extension=self._extract_extension(text),
            filesize=self._extract_size(text),
            year=self._extract_year(text),
            md5=md5,
            url=f"{base}/md5/{md5}",
        )

    @staticmethod
    def _extract_author(row) -> str:
        for a in row.select("a[href^='/search?q=']")[:1]:
            return a.get_text(" ", strip=True)
        return ""

    @staticmethod
    def _extract_language(text: str) -> str:
        m = LANG_RE.search(text)
        return m.group(1) if m else ""

    @staticmethod
    def _extract_extension(text: str) -> str:
        m = EXT_RE.search(text)
        return m.group(1).lower() if m else ""

    @staticmethod
    def _extract_size(text: str) -> str:
        m = SIZE_RE.search(text)
        return m.group(1).replace(" ", "") if m else ""

    @staticmethod
    def _extract_year(text: str) -> str:
        m = YEAR_RE.search(text)
        return m.group(0) if m else ""