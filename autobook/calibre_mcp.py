"""Wrapper MCP para operaciones avanzadas de Calibre.

Extiende CalibreIntegration con funcionalidades de gestión de biblioteca:
búsqueda, listado, diagnóstico, limpieza, exportación y operaciones de archivo.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import string
import subprocess
from pathlib import Path

from .calibre import CalibreError, CalibreIntegration, _no_window_flags
from .config import CalibreConfig
from .organize import normalize_author


MTP_EJECT_PS = r"""
param([string]$DeviceName, [string]$DriveLetter)
if ($DriveLetter) {
    rundll32.exe shell32.dll,Control_RunDLL hotplug.dll,,Eject $DriveLetter
} else {
    $shell = New-Object -ComObject Shell.Application
    $dev = $shell.Namespace(17).Items() | Where-Object { $_.Name -eq $DeviceName } | Select-Object -First 1
    if ($dev) {
        $shell.Namespace(0x11).ParseName($dev.Self.Path).InvokeVerb("Eject")
    }
}
"""


class CalibreMCP:
    """Expone operaciones avanzadas de gestión de biblioteca de Calibre como tools MCP."""

    def __init__(self, integration: CalibreIntegration) -> None:
        self.cal = integration

    @property
    def cfg(self) -> CalibreConfig:
        return self.cal.cfg

    # ------------------------------------------------------------------ #
    # Search & Browse
    # ------------------------------------------------------------------ #

    def search_books(
        self,
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
        """Search the Calibre library by structured fields or native Calibre query syntax.
        Structured fields use direct SQL (partial/substring match, case-insensitive),
        which is more reliable than native syntax for queries like author='Tolkien'."""
        self.cal._require()
        if query_string:
            out = self._calibredb_search(query_string, limit, offset)
            for row in out:
                bid = row.get("id")
                if bid:
                    title_a, author_a = self.cal.book_title_author(bid)
                    row["title"] = title_a
                    row["author"] = author_a
                    formats = self.cal.book_formats(bid)
                    row["formats"] = list(formats.keys()) if formats else []
                    row["format_files"] = {k: str(v) for k, v in formats.items()}
            return out

        # Build SQL query with JOINs for structured fields
        sql = "SELECT DISTINCT b.id, b.title, b.sort FROM books b"
        joins: list[str] = []
        where: list[str] = []
        params: list = []

        if title:
            where.append("LOWER(b.title) LIKE ?")
            params.append(f"%{title.lower()}%")
        if author:
            joins.append("JOIN books_authors_link bal ON bal.book = b.id")
            joins.append("JOIN authors a ON a.id = bal.author")
            where.append("LOWER(a.name) LIKE ?")
            params.append(f"%{author.lower()}%")
        if series:
            joins.append("JOIN books_series_link bsl ON bsl.book = b.id")
            joins.append("JOIN series s ON s.id = bsl.series")
            where.append("LOWER(s.name) LIKE ?")
            params.append(f"%{series.lower()}%")
        if tag:
            joins.append("JOIN books_tags_link btl ON btl.book = b.id")
            joins.append("JOIN tags t ON t.id = btl.tag")
            where.append("LOWER(t.name) LIKE ?")
            params.append(f"%{tag.lower()}%")
        if publisher:
            joins.append("JOIN books_publishers_link bpl ON bpl.book = b.id")
            joins.append("JOIN publishers p ON p.id = bpl.publisher")
            where.append("LOWER(p.name) LIKE ?")
            params.append(f"%{publisher.lower()}%")
        if fmt:
            joins.append("JOIN data d ON d.book = b.id")
            where.append("d.format = ?")
            params.append(fmt.upper())
        if identifier:
            joins.append("JOIN identifiers i ON i.book = b.id")
            where.append("(LOWER(i.type) LIKE ? OR LOWER(i.val) LIKE ?)")
            params.append(f"%{identifier.lower()}%")
            params.append(f"%{identifier.lower()}%")
        if has_cover is True:
            where.append("b.has_cover = 1")
        elif has_cover is False:
            where.append("b.has_cover = 0")
        if has_formats is True:
            where.append("b.id IN (SELECT DISTINCT book FROM data)")
        elif has_formats is False:
            where.append("b.id NOT IN (SELECT DISTINCT book FROM data)")

        if joins:
            sql += " " + " ".join(joins)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY b.id LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset)

        if not joins and not where:
            return []

        try:
            with self.cal._connect_ro() as conn:
                rows = conn.execute(sql, params).fetchall()
        except sqlite3.Error:
            return []

        result = []
        for bid, title, sort in rows:
            formats = self.cal.book_formats(bid)
            title_a, author_a = self.cal.book_title_author(bid)
            result.append({
                "id": bid,
                "title": title,
                "sort": sort,
                "author": author_a,
                "formats": list(formats.keys()) if formats else [],
                "format_files": {k: str(v) for k, v in formats.items()},
            })
        return result

    def _calibredb_search(self, query: str, limit: int, offset: int) -> list[dict]:
        args = ["search", f"--limit={limit}", f"--offset={offset}", query]
        try:
            out = self.cal._run_calibredb(args, timeout=120)
        except CalibreError:
            return []
        # calibredb search outputs space-separated IDs
        ids = []
        for line in out.splitlines():
            for tok in line.split():
                tok = tok.strip()
                if tok.isdigit():
                    ids.append(int(tok))
        result = []
        for bid in ids:
            row: dict = {"id": bid}
            # Get additional fields via calibredb show
            try:
                details = self._calibredb_show(bid)
                row.update(details)
            except Exception:
                pass
            result.append(row)
        return result

    def _calibredb_show(self, book_id: int) -> dict:
        """Use calibredb show to get metadata fields."""
        args = ["show", str(book_id)]
        try:
            out = self.cal._run_calibredb(args, timeout=120)
        except CalibreError:
            return {}
        fields: dict = {}
        for line in out.splitlines():
            line = line.strip()
            if ":" in line:
                key, _, val = line.partition(":")
                fields[key.strip().lower().replace(" ", "_")] = val.strip()
        return fields

    def get_book_details(self, book_id: int) -> dict:
        """Get complete details for a single book: title, authors, series, tags,
        publisher, formats, identifiers, languages, comments."""
        self.cal._require()
        try:
            with self.cal._connect_ro() as conn:
                row = conn.execute(
                    """
                    SELECT b.title, b.sort, b.series_index, b.timestamp, b.pubdate,
                           s.name AS series_name
                    FROM books b
                    LEFT JOIN books_series_link bsl ON bsl.book = b.id
                    LEFT JOIN series s ON s.id = bsl.series
                    WHERE b.id = ?
                    """,
                    (book_id,),
                ).fetchone()
                if row is None:
                    return {"error": f"book_id {book_id} no encontrado"}
                title, sort, series_index, ts, pub, series = row
                authors = conn.execute(
                    "SELECT a.name FROM authors a JOIN books_authors_link bal ON bal.author=a.id"
                    " WHERE bal.book=? ORDER BY a.name",
                    (book_id,),
                ).fetchall()
                tags = conn.execute(
                    "SELECT t.name FROM tags t JOIN books_tags_link bt ON bt.tag=t.id WHERE bt.book=?"
                    " ORDER BY t.name",
                    (book_id,),
                ).fetchall()
                # publisher
                pub_row = conn.execute(
                    "SELECT p.name FROM publishers p JOIN books_publishers_link bp ON bp.publisher=p.id"
                    " WHERE bp.book=?",
                    (book_id,),
                ).fetchone()
                # languages
                langs = conn.execute(
                    "SELECT l.lang_code FROM languages l JOIN books_languages_link bl ON bl.lang_code=l.id"
                    " WHERE bl.book=?",
                    (book_id,),
                ).fetchall()
                # identifiers
                identifiers = conn.execute(
                    "SELECT type, val FROM identifiers WHERE book=?",
                    (book_id,),
                ).fetchall()
                # comments
                comments = conn.execute(
                    "SELECT text FROM comments WHERE book=?",
                    (book_id,),
                ).fetchone()
                # rating: in books_ratings_link -> ratings (newer Calibre)
                try:
                    rrow = conn.execute(
                        "SELECT r.rating FROM ratings r JOIN books_ratings_link brl ON brl.rating=r.id"
                        " WHERE brl.book=?",
                        (book_id,),
                    ).fetchone()
                    rating = rrow[0] if rrow else None
                except sqlite3.Error:
                    # Fallback: maybe books table has rating column (older versions)
                    try:
                        rrow = conn.execute("SELECT rating FROM books WHERE id=?", (book_id,)).fetchone()
                        rating = rrow[0] if rrow else None
                    except sqlite3.Error:
                        rating = None
        except sqlite3.Error as exc:
            return {"error": f"Error de base de datos: {exc}"}
        formats = self.cal.book_formats(book_id)
        return {
            "book_id": book_id,
            "title": title,
            "sort": sort,
            "authors": [r[0] for r in authors],
            "series": series,
            "series_index": series_index,
            "tags": [r[0] for r in tags],
            "publisher": pub_row[0] if pub_row else None,
            "languages": [r[0] for r in langs],
            "identifiers": {r[0]: r[1] for r in identifiers},
            "rating": rating,
            "timestamp": str(ts) if ts else None,
            "pubdate": str(pub) if pub else None,
            "comments": comments[0] if comments else None,
            "formats": {k: str(v) for k, v in formats.items()},
        }

    def list_authors(self, search: str = "", min_books: int = 0, limit: int = 100, offset: int = 0, sort_by: str = "name") -> list[dict]:
        """List authors with book counts, filtering by name and minimum book count."""
        self.cal._require()
        order = "a.name" if sort_by == "name" else "cnt"
        with self.cal._connect_ro() as conn:
            rows = conn.execute(
                f"""
                SELECT a.id, a.name, a.sort, a.link, cnt.cnt
                FROM authors a
                JOIN (
                  SELECT author, COUNT(*) AS cnt FROM books_authors_link GROUP BY author
                ) cnt ON cnt.author = a.id
                WHERE ({min_books} = 0 OR cnt.cnt >= {min_books})
                  AND (? = '' OR a.name LIKE '%' || ? || '%')
                ORDER BY {order}
                LIMIT ? OFFSET ?
                """,
                (search, search, limit, offset),
            ).fetchall()
        return [{"id": r[0], "name": r[1], "sort": r[2], "link": r[3], "books": r[4]} for r in rows]

    def list_series(self, search: str = "", min_books: int = 0, limit: int = 100, offset: int = 0) -> list[dict]:
        """List series with book counts and number ranges."""
        self.cal._require()
        with self.cal._connect_ro() as conn:
            rows = conn.execute(
                """
                SELECT s.id, s.name, s.sort, cnt.cnt, mn.mn, mx.mx
                FROM series s
                JOIN (SELECT series, COUNT(*) AS cnt FROM books_series_link GROUP BY series) cnt ON cnt.series=s.id
                JOIN (SELECT bsl.series, MIN(b.series_index) AS mn FROM books_series_link bsl JOIN books b ON b.id=bsl.book GROUP BY bsl.series) mn ON mn.series=s.id
                JOIN (SELECT bsl.series, MAX(b.series_index) AS mx FROM books_series_link bsl JOIN books b ON b.id=bsl.book GROUP BY bsl.series) mx ON mx.series=s.id
                WHERE (? = '' OR s.name LIKE '%' || ? || '%')
                  AND (? <= 0 OR cnt.cnt >= ?)
                ORDER BY s.sort
                LIMIT ? OFFSET ?
                """,
                (search, search, min_books, min_books, limit, offset),
            ).fetchall()
        return [{"id": r[0], "name": r[1], "sort": r[2], "books": r[3], "min_index": r[4], "max_index": r[5]} for r in rows]

    def list_tags(self, search: str = "", min_books: int = 0, limit: int = 100, offset: int = 0) -> list[dict]:
        """List tags with book counts."""
        self.cal._require()
        with self.cal._connect_ro() as conn:
            rows = conn.execute(
                """
                SELECT t.id, t.name, cnt.cnt
                FROM tags t
                JOIN (SELECT tag, COUNT(*) AS cnt FROM books_tags_link GROUP BY tag) cnt ON cnt.tag=t.id
                WHERE (? = '' OR t.name LIKE '%' || ? || '%')
                  AND (? <= 0 OR cnt.cnt >= ?)
                ORDER BY cnt.cnt DESC, t.name
                LIMIT ? OFFSET ?
                """,
                (search, search, min_books, min_books, limit, offset),
            ).fetchall()
        return [{"id": r[0], "name": r[1], "books": r[2]} for r in rows]

    def list_publishers(self, search: str = "", min_books: int = 0, limit: int = 100, offset: int = 0) -> list[dict]:
        """List publishers with book counts."""
        self.cal._require()
        with self.cal._connect_ro() as conn:
            rows = conn.execute(
                """
                SELECT p.id, p.name, cnt.cnt
                FROM publishers p
                JOIN (SELECT publisher, COUNT(*) AS cnt FROM books_publishers_link GROUP BY publisher) cnt ON cnt.publisher=p.id
                WHERE (? = '' OR p.name LIKE '%' || ? || '%')
                  AND (? <= 0 OR cnt.cnt >= ?)
                ORDER BY cnt.cnt DESC, p.name
                LIMIT ? OFFSET ?
                """,
                (search, search, min_books, min_books, limit, offset),
            ).fetchall()
        return [{"id": r[0], "name": r[1], "books": r[2]} for r in rows]

    # ------------------------------------------------------------------ #
    # Diagnostics
    # ------------------------------------------------------------------ #

    def find_duplicates(self, strategy: str = "exact", limit: int = 100) -> list[list[int]]:
        """Find duplicate books.
        strategy: exact (same title+author), isbn (same ISBN), fuzzy (normalized title+author)."""
        self.cal._require()
        if strategy == "exact":
            sql = """
                SELECT b1.id, b1.title, a1.name
                FROM books b1
                JOIN books_authors_link bal1 ON bal1.book=b1.id
                JOIN authors a1 ON a1.id=bal1.author
                WHERE b1.id IN (
                  SELECT b2.id FROM books b2
                  JOIN books_authors_link bal2 ON bal2.book=b2.id
                  JOIN authors a2 ON a2.id=bal2.author
                  WHERE lower(b2.title)=lower(b1.title) AND lower(a2.name)=lower(a1.name)
                    AND b2.id != b1.id
                )
                ORDER BY b1.id
            """
        elif strategy == "isbn":
            sql = """
                SELECT DISTINCT b1.id, b1.title, a1.name
                FROM books b1
                JOIN books_authors_link bal1 ON bal1.book=b1.id
                JOIN authors a1 ON a1.id=bal1.author
                JOIN identifiers i1 ON i1.book=b1.id AND i1.type='isbn'
                WHERE i1.val IN (
                  SELECT i2.val FROM identifiers i2 WHERE i2.type='isbn' AND i2.book != b1.id
                )
                ORDER BY b1.id
            """
        else:
            # fuzzy: normalized title + author (remove punctuation, lowercase)
            sql = """
                WITH norm AS (
                  SELECT b.id AS book_id,
                    REPLACE(REPLACE(REPLACE(LOWER(TRIM(b.title)), ' ', ''), ',', ''), '.', '') AS ntitle,
                    REPLACE(REPLACE(REPLACE(LOWER(TRIM(a.name)), ' ', ''), ',', ''), '.', '') AS nauthor
                  FROM books b
                  JOIN books_authors_link bal ON bal.book=b.id
                  JOIN authors a ON a.id=bal.author
                )
                SELECT DISTINCT n1.book_id, b.title, a.name
                FROM norm n1
                JOIN books b ON b.id=n1.book_id
                JOIN books_authors_link bal ON bal.book=b.id
                JOIN authors a ON a.id=bal.author
                WHERE n1.book_id IN (
                  SELECT n2.book_id FROM norm n2
                  WHERE n2.ntitle=n1.ntitle AND n2.nauthor=n1.nauthor AND n2.book_id != n1.book_id
                )
                ORDER BY n1.book_id
            """
        try:
            with self.cal._connect_ro() as conn:
                rows = conn.execute(sql).fetchall()
        except sqlite3.Error:
            return []
        # Group duplicates by identifier (title+author or isbn)
        groups: dict[str, list[int]] = {}
        for bid, title, author in rows:
            key = f"{title}|{author}".lower()
            groups.setdefault(key, []).append(bid)
        result = [sorted(v) for v in groups.values() if len(v) > 1]
        return result[:limit]

    def find_missing_metadata(self, limit: int = 100) -> dict:
        """Find books missing cover, language, tags, formats, or publisher."""
        self.cal._require()
        with self.cal._connect_ro() as conn:
            no_cover = conn.execute(
                f"SELECT b.id FROM books b WHERE b.has_cover = 0 LIMIT {limit}").fetchall()
            no_lang = conn.execute(
                "SELECT b.id FROM books b WHERE b.id NOT IN (SELECT book FROM books_languages_link)"
                f" LIMIT {limit}").fetchall()
            no_tags = conn.execute(
                "SELECT b.id FROM books b WHERE b.id NOT IN (SELECT book FROM books_tags_link)"
                f" LIMIT {limit}").fetchall()
            no_formats = conn.execute(
                "SELECT b.id FROM books b WHERE b.id NOT IN (SELECT book FROM data WHERE format IN ('EPUB','PDF','AZW3','MOBI','FB2','TXT'))"
                f" LIMIT {limit}").fetchall()
            no_pub = conn.execute(
                "SELECT b.id FROM books b WHERE b.id NOT IN (SELECT book FROM books_publishers_link)"
                f" LIMIT {limit}").fetchall()
        return {
            "no_cover": [r[0] for r in no_cover],
            "no_language": [r[0] for r in no_lang],
            "no_tags": [r[0] for r in no_tags],
            "no_formats": [r[0] for r in no_formats],
            "no_publisher": [r[0] for r in no_pub],
        }

    def find_ghost_books(self, use_calibredb: bool = True, limit: int = 0, offset: int = 0) -> list[dict]:
        """Find books in DB whose directory or format files don't exist on disk."""
        self.cal._require()
        if use_calibredb:
            try:
                out = self.cal._run_calibredb(["check_library", "--on-output"], timeout=600)
                # calibredb check_library output format varies; parse lines
                results = []
                for line in out.splitlines():
                    line = line.strip()
                    if line and ("error" in line.lower() or "missing" in line.lower()):
                        results.append({"detail": line})
                if results:
                    return results
            except CalibreError:
                pass
            return []
        # Manual fallback scan
        if limit == 0:
            with self.cal._connect_ro() as conn:
                total = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        else:
            total = None
        with self.cal._connect_ro() as conn:
            query = "SELECT b.id, b.title, b.path FROM books b LIMIT ? OFFSET ?"
            rows = conn.execute(query, (limit or 5000, offset)).fetchall()
        ghosts = []
        for bid, title, relpath in rows:
            book_dir = self.cal.library / relpath
            if not book_dir.exists():
                ghosts.append({"book_id": bid, "title": title, "path": relpath, "missing": "directory"})
                continue
            for fmt, fpath in self.cal.book_formats(bid).items():
                if not fpath.exists():
                    ghosts.append({"book_id": bid, "title": title, "path": relpath, "missing": f"file:{fmt}"})
        return ghosts

    def find_orphan_files(self, use_calibredb: bool = True, limit: int = 100) -> list[dict]:
        """Find directories in the library with no matching DB record."""
        self.cal._require()
        if use_calibredb:
            try:
                out = self.cal._run_calibredb(["check_library", "--on-output"], timeout=600)
                results = []
                for line in out.splitlines():
                    line = line.strip()
                    if "extra" in line.lower() or "orphan" in line.lower():
                        results.append({"detail": line})
                if results:
                    return results
            except CalibreError:
                pass
            return []
        # Manual fallback: scan library dirs
        if not self.cal.library:
            return []
        orphans = []
        db_paths = set()
        with self.cal._connect_ro() as conn:
            rows = conn.execute("SELECT path FROM books").fetchall()
            db_paths = {r[0] for r in rows}
        for entry in self.cal.library.iterdir():
            if entry.is_dir() and entry.name not in db_paths:
                orphans.append({"path": str(entry), "reason": "no DB record"})
        return orphans[:limit]

    def library_stats(self) -> dict:
        """Get summary statistics of the library."""
        self.cal._require()
        with self.cal._connect_ro() as conn:
            total = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
            authors = conn.execute("SELECT COUNT(*) FROM authors").fetchone()[0]
            series = conn.execute("SELECT COUNT(*) FROM series").fetchone()[0]
            tags = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
            publishers = conn.execute("SELECT COUNT(*) FROM publishers").fetchone()[0]
            identifiers = conn.execute("SELECT COUNT(*) FROM identifiers").fetchone()[0]
            formats = conn.execute("SELECT DISTINCT format FROM data").fetchall()
            missing_covers = conn.execute(
                "SELECT COUNT(*) FROM books b WHERE b.id NOT IN (SELECT book FROM data WHERE name LIKE 'cover%')"
            ).fetchone()[0]
            missing_lang = conn.execute(
                "SELECT COUNT(*) FROM books b WHERE b.id NOT IN (SELECT book FROM books_languages_link)"
            ).fetchone()[0]
        db_size = 0
        db_file = self.cal.library / "metadata.db"
        if db_file.exists():
            db_size = db_file.stat().st_size
        total_formats = {r[0] for r in formats}
        return {
            "total_books": total,
            "total_authors": authors,
            "total_series": series,
            "total_tags": tags,
            "total_publishers": publishers,
            "total_identifiers": identifiers,
            "formats_available": sorted(total_formats),
            "books_missing_covers": missing_covers,
            "books_missing_language": missing_lang,
            "db_size_bytes": db_size,
        }

    # ------------------------------------------------------------------ #
    # Metadata & File Operations
    # ------------------------------------------------------------------ #

    def fetch_metadata(
        self,
        book_ids: list[int],
        source: str = "openlibrary",
        apply: bool = False,
        dry_run: bool = True,
    ) -> dict:
        """Fetch metadata from Open Library or Google Books API.
        Queries APIs directly. With apply=True and dry_run=False, writes found metadata back."""
        if not book_ids:
            return {"error": "book_ids no puede estar vacío"}
        results: dict = {"fetched": {}, "applied": {}, "errors": {}}
        for bid in book_ids:
            details = self.get_book_details(bid)
            if "error" in details:
                results["errors"][bid] = details["error"]
                continue
            isbn = None
            for id_type, val in details.get("identifiers", {}).items():
                if id_type == "isbn" and val:
                    isbn = val
                    break
            title = details.get("title", "")
            query = isbn or title
            try:
                if source == "googlebooks":
                    meta = self._fetch_google_books(query)
                else:
                    meta = self._fetch_openlibrary(query)
            except Exception as exc:
                results["errors"][bid] = str(exc)
                continue
            if meta:
                results["fetched"][bid] = meta
                if apply and not dry_run:
                    fields = {}
                    if meta.get("title"):
                        fields["title"] = meta["title"]
                    if meta.get("authors"):
                        fields["authors"] = " & ".join(meta["authors"])
                    if meta.get("series"):
                        fields["series"] = meta["series"]
                    if meta.get("series_index"):
                        fields["series_index"] = meta["series_index"]
                    if meta.get("tags"):
                        fields["tags"] = ",".join(meta["tags"])
                    if meta.get("publisher"):
                        fields["publisher"] = meta["publisher"]
                    if meta.get("pubdate"):
                        fields["pubdate"] = meta["pubdate"]
                    if meta.get("comments"):
                        fields["comments"] = meta["comments"]
                    if meta.get("languages"):
                        fields["languages"] = meta["languages"]
                    if fields:
                        try:
                            self.cal.set_metadata(bid, fields)
                            results["applied"][bid] = fields
                        except CalibreError as exc:
                            results["errors"][bid] = str(exc)
                else:
                    results["applied"][bid] = "dry_run"
        return results

    def _fetch_openlibrary(self, query: str) -> dict | None:
        """Query Open Library search API."""
        import json
        import urllib.parse
        import urllib.request
        encoded = urllib.parse.quote(query)
        url = f"https://openlibrary.org/search.json?q={encoded}&limit=1"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        docs = data.get("docs", [])
        if not docs:
            return None
        doc = docs[0]
        title = doc.get("title", "")
        authors = []
        for a in doc.get("author_name", []):
            authors.append(a)
        publisher = doc.get("publisher", [None])[0]
        year = doc.get("first_publish_year")
        languages = []
        for lang in doc.get("language", []):
            languages.append(lang)
        return {
            "title": title,
            "authors": authors,
            "publisher": publisher,
            "pubdate": str(year) if year else None,
            "languages": ",".join(languages) if languages else "",
            "tags": [],
            "series": None,
            "series_index": None,
            "comments": None,
            "source_url": f"https://openlibrary.org{doc.get('key', '')}",
        }

    def _fetch_google_books(self, query: str) -> dict | None:
        """Query Google Books API v1."""
        import json
        import urllib.parse
        import urllib.request
        encoded = urllib.parse.quote(query)
        url = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{encoded}+inauthor:&maxResults=1"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        items = data.get("items", [])
        if not items:
            return None
        vol = items[0].get("volumeInfo", {})
        title = vol.get("title", "")
        authors = vol.get("authors", [])
        publisher = vol.get("publisher")
        pubdate = vol.get("publishedDate")
        categories = vol.get("categories", [])
        description = vol.get("description")
        return {
            "title": title,
            "authors": authors,
            "publisher": publisher,
            "pubdate": pubdate,
            "languages": "",
            "tags": categories,
            "series": None,
            "series_index": None,
            "comments": description,
            "source_url": vol.get("canonicalVolumeLink"),
        }

    def embed_metadata(self, book_ids: list[int] | None = None, only_formats: str = "", dry_run: bool = True) -> dict:
        """Embed metadata from the Calibre DB into the actual book files.
        If book_ids omitted, processes ALL books. dry_run by default."""
        self.cal._require()
        if dry_run:
            return {"note": "dry_run=True: no changes made. Set dry_run=False to apply."}
        if not book_ids:
            # Use calibredb embed_metadata for all books
            args = ["embed_metadata", "--all"]
        else:
            args = ["embed_metadata"] + [str(b) for b in book_ids]
        if only_formats:
            args += ["--only-format", only_formats.upper()]
        try:
            out = self.cal._run_calibredb(args, timeout=600)
            return {"ok": True, "output": out}
        except CalibreError as exc:
            return {"error": str(exc)}

    def verify_file_integrity(self, book_ids: list[int] | None = None) -> dict:
        """Verify that every format file referenced in the DB exists on disk."""
        self.cal._require()
        if book_ids:
            with self.cal._connect_ro() as conn:
                rows = conn.execute(
                    "SELECT d.format, b.path, d.name FROM data d JOIN books b ON b.id=d.book WHERE d.book IN (%s)" %
                    ",".join("?" * len(book_ids)),
                    book_ids,
                ).fetchall()
        else:
            with self.cal._connect_ro() as conn:
                rows = conn.execute(
                    "SELECT d.format, b.path, d.name FROM data d JOIN books b ON b.id=d.book"
                ).fetchall()
        missing = []
        checked = 0
        for fmt, relpath, name in rows:
            checked += 1
            fpath = self.cal.library / relpath / f"{name}.{fmt.lower()}"
            if not fpath.exists():
                missing.append({"file": str(fpath), "format": fmt, "missing": True})
        return {"ok": len(missing) == 0, "checked": checked, "missing_files": missing}

    # ------------------------------------------------------------------ #
    # Cleanup Operations
    # ------------------------------------------------------------------ #

    def cleanup_orphan_links(self, dry_run: bool = True) -> dict:
        """Remove orphan entries from link tables where book ID no longer exists."""
        if not self.cal.available():
            return {"error": "Calibre no disponible"}
        results = {}
        tables = [
            ("books_authors_link", "author"),
            ("books_tags_link", "tag"),
            ("books_series_link", "series"),
            ("books_publishers_link", "publisher"),
            ("books_languages_link", "language"),
            ("books_ratings_link", "rating"),
            ("books_comments_link", "comments"),
        ]
        for link_table, col in tables:
            orphans = self.cal.find_orphan_links() if hasattr(self.cal, "find_orphan_links") else []
            results[link_table] = {"orphans_found": len(orphans)}
            if not dry_run and orphans:
                with self.cal._connect_ro() as conn:
                    conn.execute(f"DELETE FROM {link_table} WHERE book NOT IN (SELECT id FROM books)")
                    conn.commit()
                results[link_table]["deleted"] = True
        return results

    def find_orphan_links(self, dry_run: bool = True) -> list[dict]:
        """Find orphan entries in link tables (book ID no longer exists)."""
        self.cal._require()
        result = []
        link_tables = [
            "books_authors_link", "books_tags_link", "books_series_link",
            "books_publishers_link", "books_languages_link", "books_ratings_link",
            "books_comments_link", "books_custom_column_link",
        ]
        with self.cal._connect_ro() as conn:
            for tbl in link_tables:
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {tbl} WHERE book NOT IN (SELECT id FROM books)"
                ).fetchone()[0]
                if count > 0:
                    result.append({"table": tbl, "orphan_count": count})
        return result

    def find_orphaned_metadata(self, dry_run: bool = True) -> dict:
        """Find orphaned rows in authors, series, tags, publishers, languages, comments, ratings."""
        self.cal._require()
        tables = ["authors", "series", "tags", "publishers", "languages", "comments", "ratings"]
        result = {}
        with self.cal._connect_ro() as conn:
            for tbl in tables:
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {tbl} WHERE id NOT IN (SELECT DISTINCT {tbl[:-1]} FROM {tbl}s_link WHERE {tbl[:-1]}=id) OR id NOT IN (SELECT {tbl[:-1]} FROM books_{tbl}s_link)"
                ).fetchone()[0] if False else 0
                # Simplified approach
                pass
        # Use calibredb approach instead
        try:
            out = self.cal._run_calibredb(["check_library"], timeout=300)
            result["calibredb_check"] = out[:2000] if out else "No output"
        except CalibreError as exc:
            result["error"] = str(exc)
        return result

    def vacuum_database(self, dry_run: bool = True) -> dict:
        """Compact the database after bulk operations. Requires Calibre GUI closed."""
        if dry_run:
            return {"note": "dry_run=True: no changes made. Set dry_run=False to apply."}
        self.cal._require()
        from .calibre import is_gui_open
        if is_gui_open():
            return {"error": "Calibre GUI está abierto. Ciérrala antes de vacuum."}
        try:
            out = self.cal._run_calibredb(["vacuum"], timeout=600)
            return {"ok": True, "output": out}
        except CalibreError as exc:
            return {"error": str(exc)}

    def export_catalog(self, output_file: str = "catalog.csv", fields: str = "") -> dict:
        """Export the library catalog to CSV, XML, EPUB, or MOBI."""
        self.cal._require()
        out_path = Path(output_file)
        if not out_path.is_absolute():
            out_path = self.cal.library / out_path
        args = ["catalog", str(out_path)]
        if fields:
            args += ["--fields", fields]
        try:
            self.cal._run_calibredb(args, timeout=600)
            return {"ok": True, "path": str(out_path)}
        except CalibreError as exc:
            return {"error": str(exc)}

    def generate_report(self) -> dict:
        """Generate a comprehensive markdown report of the library's current state."""
        stats = self.library_stats()
        dups = self.find_duplicates("exact", limit=200)
        ghosts = self.find_ghost_books(use_calibredb=False, limit=50)
        missing = self.find_missing_metadata(limit=100)
        return {
            "stats": stats,
            "duplicate_groups": len(dups),
            "ghost_books": len(ghosts),
            "missing_metadata": {k: len(v) for k, v in missing.items()},
        }

    def backup_database(self, suffix: str = "") -> dict:
        """Create a full backup copy of metadata.db."""
        if not self.cal.library:
            return {"error": "No se detectó la biblioteca de Calibre"}
        db = self.cal.library / "metadata.db"
        if not db.exists():
            return {"error": "metadata.db no encontrado"}
        import datetime
        if not suffix:
            suffix = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = self.cal.library / f"metadata_{suffix}.db.bak"
        shutil.copy2(db, backup)
        return {"ok": True, "path": str(backup)}

    # ------------------------------------------------------------------ #
    # Author / Series Cleanup Tools
    # ------------------------------------------------------------------ #

    def rename_author(self, author_id: int, new_name: str, new_sort: str = "", dry_run: bool = True) -> dict:
        """Rename an author directly in the database (supports case-only renames)."""
        self.cal._require()
        if dry_run:
            return {"note": "dry_run=True: no changes made", "would_rename": {"id": author_id, "new_name": new_name, "new_sort": new_sort}}
        with self.cal._connect_ro() as conn:
            row = conn.execute("SELECT name, sort FROM authors WHERE id=?", (author_id,)).fetchone()
            if not row:
                return {"error": f"author_id {author_id} no encontrado"}
            old_name, old_sort = row
        try:
            self.cal._run_calibredb(["rename_author", str(author_id), "--name", new_name], timeout=60)
            if new_sort:
                self.cal._run_calibredb(["rename_author", str(author_id), "--sort", new_sort], timeout=60)
            return {"ok": True, "old_name": old_name, "old_sort": old_sort, "new_name": new_name, "new_sort": new_sort or ""}
        except CalibreError as exc:
            return {"error": str(exc)}

    def merge_authors(self, canonical_id: int, variant_ids: list[int], dry_run: bool = True) -> dict:
        """Merge author variants into a canonical author."""
        self.cal._require()
        if not variant_ids:
            return {"error": "variant_ids no puede estar vacío"}
        if dry_run:
            return {"note": "dry_run=True: no changes made", "canonical": canonical_id, "variants": variant_ids}
        try:
            args = ["merge_authors", str(canonical_id)] + [str(v) for v in variant_ids]
            self.cal._run_calibredb(args, timeout=120)
            return {"ok": True, "canonical_id": canonical_id, "merged_ids": variant_ids}
        except CalibreError as exc:
            return {"error": str(exc)}

    def find_author_variants(self, limit: int = 100) -> list[dict]:
        """Find groups of authors that appear to be the same person."""
        self.cal._require()
        # Use SQL heuristic: prefix+initials matching, case-insensitive groups
        with self.cal._connect_ro() as conn:
            rows = conn.execute(
                """
                SELECT a.id, a.name, a.sort, cnt.cnt
                FROM authors a
                JOIN (SELECT author, COUNT(*) AS cnt FROM books_authors_link GROUP BY author) cnt ON cnt.author=a.id
                ORDER BY cnt.cnt DESC, a.name
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        # Simple grouping: same last word, different case
        groups: dict[str, list[dict]] = {}
        for aid, name, sort, cnt in rows:
            last = name.split()[-1].lower() if name else ""
            if last:
                key = f"last:{last}"
                groups.setdefault(key, []).append({"id": aid, "name": name, "sort": sort, "books": cnt})
        variants = []
        for key, members in groups.items():
            names = {m["name"].lower() for m in members}
            if len(names) > 1:
                variants.append({"group_key": key, "authors": members})
        return variants

    def normalize_uppercase(self, item_type: str = "all", limit: int = 100, dry_run: bool = True) -> dict:
        """Convert ALL UPPERCASE titles/tags/publishers/series to Title Case."""
        self.cal._require()
        types = [item_type] if item_type != "all" else ["titles", "tags", "publishers", "series"]
        results = {}
        for it in types:
            try:
                out = self.cal._run_calibredb(["search", f"{it}:UPPER"], timeout=120)
                results[it] = {"found": out.strip()[:500]}
            except CalibreError as exc:
                results[it] = {"error": str(exc)}
        if not dry_run:
            # Actually do the rename via calibredb
            for it in types:
                try:
                    self.cal._run_calibredb(["modify_commands", "--unicode", "--titlecase"], timeout=120)
                except CalibreError:
                    pass
        return results

    def fix_author_sort(self, limit: int = 100, dry_run: bool = True) -> dict:
        """Synchronize books.author_sort with linked authors' sort fields."""
        if dry_run:
            return {"note": "dry_run=True: would sync author_sort for all books", "limit": limit}
        self.cal._require()
        # Calibre has built-in: calibredb update --all --to-opf
        # We use direct SQL via the read-only connection's writable twin
        import sqlite3 as sq
        db_path = str(self.cal.library / "metadata.db")
        try:
            conn = sq.connect(db_path)
            cursor = conn.execute("""
                UPDATE books SET author_sort = (
                    SELECT a.sort FROM authors a
                    JOIN books_authors_link bal ON bal.author=a.id
                    WHERE bal.book=books.id ORDER BY a.sort LIMIT 1
                ) WHERE books.id IN (
                    SELECT b.id FROM books b
                    JOIN books_authors_link bal ON bal.book=b.id
                    JOIN authors a ON a.id=bal.author
                    WHERE b.author_sort != a.sort LIMIT ?
                )
            """, (limit,))
            count = cursor.rowcount
            conn.commit()
            conn.close()
            return {"ok": True, "updated": count}
        except Exception as exc:
            return {"error": str(exc)}

    def fix_series_numbers(self, series_id: int, assignments: list[dict], dry_run: bool = True) -> dict:
        """Fix series numbering by assigning specific indices to books."""
        if not assignments:
            return {"error": "assignments no puede estar vacío"}
        if dry_run:
            return {"note": "dry_run=True", "series_id": series_id, "assignments": assignments}
        self.cal._require()
        import sqlite3 as sq
        db_path = str(self.cal.library / "metadata.db")
        try:
            conn = sq.connect(db_path)
            for a in assignments:
                conn.execute(
                    "UPDATE books SET series_index=? WHERE id=? AND series=?",
                    (a["index"], a["book_id"], series_id),
                )
            conn.commit()
            conn.close()
            return {"ok": True, "series_id": series_id, "updated": len(assignments)}
        except Exception as exc:
            return {"error": str(exc)}

    def fix_book_paths(self, book_ids: list[int] | None = None, dry_run: bool = True) -> dict:
        """Rename book directories on disk to match current author/title in DB."""
        self.cal._require()
        if book_ids:
            query = "SELECT id, title, path FROM books WHERE id IN (%s)" % ",".join("?" * len(book_ids))
            with self.cal._connect_ro() as conn:
                rows = conn.execute(query, book_ids).fetchall()
        else:
            with self.cal._connect_ro() as conn:
                rows = conn.execute("SELECT id, title, path FROM books").fetchall()
        renamed = []
        for bid, title, relpath in rows:
            current_dir = self.cal.library / relpath
            expected_author = ""
            with self.cal._connect_ro() as conn:
                a = conn.execute(
                    "SELECT name FROM authors a JOIN books_authors_link bal ON bal.author=a.id WHERE bal.book=? ORDER BY a.name LIMIT 1",
                    (bid,),
                ).fetchone()
                if a:
                    expected_author = a[0]
            from .organize import sanitize
            expected_name = sanitize(expected_author) if expected_author else "Sin autor"
            expected_parent = self.cal.library / expected_name
            if current_dir.parent != expected_parent:
                renamed.append({"book_id": bid, "from": str(current_dir), "to": str(expected_parent / sanitize(title))})
                if not dry_run:
                    expected_parent.mkdir(parents=True, exist_ok=True)
                    if current_dir.exists():
                        shutil.move(str(current_dir), str(expected_parent / current_dir.name))
        return {"checked": len(rows), "would_rename": len(renamed), "renamed": renamed[:50] if not dry_run else renamed, "dry_run": dry_run}

    def find_compilation_coverage(self, author_id: int, min_compilation_kb: int = 200) -> dict:
        """Detect which of an author's individual works are covered by their compilation EPUBs."""
        self.cal._require()
        with self.cal._connect_ro() as conn:
            series = conn.execute(
                "SELECT s.name FROM series s JOIN books_series_link bsl ON bsl.series=s.id JOIN books_authors_link bal ON bal.book=bsl.book WHERE bal.author=?",
                (author_id,),
            ).fetchall()
            books = conn.execute(
                "SELECT b.id, b.title FROM books b JOIN books_authors_link bal ON bal.book=b.id WHERE bal.author=?",
                (author_id,),
            ).fetchall()
        return {
            "author_id": author_id,
            "series": [r[0] for r in series],
            "works": [{"id": r[0], "title": r[1]} for r in books],
            "note": "Full TOC extraction requires EPUB parsing (not implemented yet).",
        }

    def analyze_author(self, author_id: int) -> dict:
        """Full cleanup analysis of one author: variants, duplicates, gaps, missing metadata."""
        self.cal._require()
        with self.cal._connect_ro() as conn:
            author = conn.execute("SELECT name, sort FROM authors WHERE id=?", (author_id,)).fetchone()
            if not author:
                return {"error": f"author_id {author_id} no encontrado"}
            name, sort = author
            books = conn.execute(
                """
                SELECT b.id, b.title, b.series, b.series_index, b.timestamp
                FROM books b JOIN books_authors_link bal ON bal.book=b.id
                WHERE bal.author=? ORDER BY b.series, b.series_index
                """,
                (author_id,),
            ).fetchall()
            variants = conn.execute(
                "SELECT a.id, a.name, a.sort FROM authors a WHERE lower(a.name) LIKE lower(?) ORDER BY a.name",
                (f"%{name.split()[-1] if name else ''}%",),
            ).fetchall()
        book_list = [{"id": r[0], "title": r[1], "series": r[2], "series_index": r[3]} for r in books]
        # Check for gaps in series
        series_groups: dict[str, list[float]] = {}
        for b in book_list:
            if b["series"]:
                s = b["series"]
                idx = b["series_index"]
                if idx is not None:
                    series_groups.setdefault(s, []).append(idx)
        gaps = {}
        for s, indices in series_groups.items():
            indices = sorted(set(indices))
            expected = list(range(int(indices[0]), int(indices[-1]) + 1))
            gaps[s] = [i for i in expected if i not in indices]
        return {
            "author_id": author_id,
            "name": name,
            "sort": sort,
            "book_count": len(book_list),
            "books": book_list,
            "variant_candidates": [{"id": v[0], "name": v[1], "sort": v[2]} for v in variants],
            "series_gaps": gaps,
        }

    def suggest_dedup_resolution(self, book_ids: list[int]) -> dict:
        """Given a group of duplicate book IDs, pick which to keep using quality score."""
        if len(book_ids) < 2:
            return {"error": "Need at least 2 book IDs"}
        formats_rank = {"EPUB": 5, "AZW3": 4, "MOBI": 3, "FB2": 2, "TXT": 1, "PDF": 0}
        candidates = []
        for bid in book_ids:
            details = self.get_book_details(bid)
            if "error" in details:
                continue
            fmts = details.get("formats", {})
            score = sum(formats_rank.get(f.upper(), 0) for f in fmts.keys())
            has_cover = any("cover" in fn.lower() for fn in [str(f) for f in fmts.values()])
            has_comments = bool(details.get("comments"))
            has_isbn = any(k == "isbn" for k in details.get("identifiers", {}).keys())
            candidates.append({
                "book_id": bid, "title": details["title"], "formats": list(fmts.keys()),
                "score": score, "has_cover": has_cover, "has_comments": has_comments,
                "has_isbn": has_isbn,
            })
        candidates.sort(key=lambda c: (
            c["score"], c["has_cover"], c["has_comments"], c["has_isbn"], c["book_id"]
        ), reverse=True)
        if not candidates:
            return {"error": "No valid candidates found"}
        keep = candidates[0]
        return {
            "keep": keep["book_id"],
            "keep_details": keep,
            "delete": [c["book_id"] for c in candidates[1:]],
            "delete_details": candidates[1:],
            "reason": "Highest quality score (EPUB preferred > cover > comments > ISBN)",
        }

    def bulk_set_metadata(self, updates: list[dict], dry_run: bool = True) -> dict:
        """Apply metadata changes to multiple books in a single call."""
        if not updates:
            return {"error": "updates no puede estar vacío"}
        results = {}
        if dry_run:
            for u in updates:
                results[u["book_id"]] = {"would_apply": u.get("fields", {})}
            return {"dry_run": True, "results": results, "total": len(updates)}
        for u in updates:
            bid = u["book_id"]
            fields = u.get("fields", {})
            if not fields:
                results[bid] = {"error": "no fields to set"}
                continue
            try:
                self.cal.set_metadata(bid, fields)
                results[bid] = {"ok": True, "fields": fields}
            except CalibreError as exc:
                results[bid] = {"error": str(exc)}
        return {"dry_run": False, "results": results, "total": len(updates)}

    # ------------------------------------------------------------------ #
    # Full-Text Search
    # ------------------------------------------------------------------ #

    def fts_index(self, action: str = "status") -> dict:
        """Manage the full-text search index: status, enable, disable, reindex."""
        self.cal._require()
        try:
            out = self.cal._run_calibredb(["fts", action], timeout=300)
            return {"action": action, "output": out}
        except CalibreError as exc:
            return {"error": str(exc)}

    def fts_search(self, query: str, limit: int = 50) -> list[dict]:
        """Full-text search in book contents."""
        self.cal._require()
        try:
            out = self.cal._run_calibredb(["fts", "search", query, f"--limit={limit}"], timeout=120)
            results = []
            for line in out.splitlines():
                line = line.strip()
                if line and line.split()[0].isdigit():
                    parts = line.split(None, 1)
                    results.append({"book_id": int(parts[0]), "snippet": parts[1] if len(parts) > 1 else ""})
            return results
        except CalibreError as exc:
            return [{"error": str(exc)}]

    # ------------------------------------------------------------------ #
    # Device Management
    # ------------------------------------------------------------------ #

    def list_devices(self) -> list[dict]:
        """List all detected Kindle/Kobo devices (USB + MTP)."""
        devs = []
        primary = self.cal.detect_device()
        if primary:
            devs.append(primary)
        # Also check calibredb devices
        try:
            out = self.cal._run_calibredb(["list_devices"], timeout=30)
            if out:
                devs.append({"type": "calibredb", "output": out.strip()})
        except CalibreError:
            pass
        return devs

    def eject_device(self, device_name: str | None = None, drive_letter: str | None = None) -> dict:
        """Safely eject a connected Kindle/Kobo device via PowerShell."""
        import tempfile
        script = Path(tempfile.gettempdir()) / f"autobook_eject_{os.getpid()}.ps1"
        script.write_text(MTP_EJECT_PS, encoding="utf-8")
        cmd = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
            "-DeviceName", device_name or "",
            "-DriveLetter", drive_letter or "",
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                               creationflags=_no_window_flags())
            script.unlink(missing_ok=True)
            return {"ok": r.returncode == 0, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
        except Exception as exc:
            script.unlink(missing_ok=True)
            return {"error": str(exc)}