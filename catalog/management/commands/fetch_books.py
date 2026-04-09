"""
Fetch books from the Open Library API and save them to the database.

Searches by subject/genre using the Open Library Search API.
Covers are pulled from the Open Library Covers API.
Full descriptions are optionally fetched from the Works API.

Usage:
    python manage.py fetch_books
    python manage.py fetch_books --subjects fiction mystery thriller --limit 100
    python manage.py fetch_books --limit 200 --fetch-descriptions
    python manage.py fetch_books --clear
"""

import time
import requests
from django.core.management.base import BaseCommand
from catalog.models import Book, Author, Genre

SEARCH_URL  = "https://openlibrary.org/search.json"
COVER_URL   = "https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"

DEFAULT_SUBJECTS = [
    "fiction",
    "mystery",
    "romance",
    "science_fiction",
    "fantasy",
    "thriller",
    "biography",
    "history",
    "horror",
    "adventure",
]

# Fields to request from the search API (keeps responses small)
SEARCH_FIELDS = ",".join([
    "key",
    "title",
    "author_name",
    "subject",
    "cover_i",
    "first_sentence",
])


class Command(BaseCommand):
    help = "Fetch books from Open Library API by subject and save to database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--subjects",
            nargs="+",
            default=DEFAULT_SUBJECTS,
            metavar="SUBJECT",
            help="One or more subjects to fetch (default: 10 popular genres)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Max books to fetch per subject (default: 50)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing books, authors, and genres before fetching",
        )
        parser.add_argument(
            "--fetch-descriptions",
            action="store_true",
            help="Fetch full descriptions from the Works API (slower — adds ~0.5 s per book)",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write("Clearing existing data…")
            Book.objects.all().delete()
            Author.objects.all().delete()
            Genre.objects.all().delete()
            self.stdout.write(self.style.WARNING("Database cleared."))

        total_imported = 0
        total_skipped = 0

        for subject in options["subjects"]:
            self.stdout.write(f"\n[{subject}]")
            imp, skip = self._fetch_subject(
                subject,
                options["limit"],
                options["fetch_descriptions"],
            )
            total_imported += imp
            total_skipped += skip

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. {total_imported} imported, {total_skipped} skipped (already exist)."
            )
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_subject(self, subject, limit, fetch_descriptions):
        imported = 0
        skipped = 0
        page = 1
        per_page = min(limit, 100)   # Open Library max page size is 100
        remaining = limit

        while remaining > 0:
            batch = min(per_page, remaining)
            params = {
                "subject": subject,
                "limit":   batch,
                "page":    page,
                "fields":  SEARCH_FIELDS,
            }

            try:
                resp = requests.get(SEARCH_URL, params=params, timeout=15)
                resp.raise_for_status()
                docs = resp.json().get("docs", [])
            except requests.RequestException as exc:
                self.stdout.write(self.style.ERROR(f"  HTTP error on page {page}: {exc}"))
                break

            if not docs:
                break

            for doc in docs:
                ok = self._save_book(doc, fetch_descriptions)
                if ok is True:
                    imported += 1
                elif ok is False:
                    skipped += 1

            remaining -= len(docs)

            # Stop paging if Open Library returned fewer results than requested
            if len(docs) < batch:
                break

            page += 1
            time.sleep(1)  # be polite to the API

        return imported, skipped

    def _save_book(self, doc, fetch_descriptions):
        """
        Create a Book record from an Open Library search result doc.
        Returns True on insert, False if skipped (duplicate), None on bad data.
        """
        title = doc.get("title", "").strip()
        if not title:
            return None

        # --- Author ---
        author_obj = None
        author_names = doc.get("author_name") or []
        if author_names:
            full_name = author_names[0].strip()
            parts = full_name.rsplit(" ", 1)
            first = parts[0] if len(parts) > 1 else full_name
            last  = parts[1] if len(parts) > 1 else ""
            author_obj, _ = Author.objects.get_or_create(
                first_name=first,
                last_name=last,
            )

        # --- Deduplicate ---
        if Book.objects.filter(title=title, author=author_obj).exists():
            return False

        # --- Summary ---
        summary = ""
        if fetch_descriptions:
            work_key = doc.get("key", "")
            if work_key:
                summary = self._fetch_description(work_key)
                time.sleep(0.5)

        if not summary:
            # first_sentence is returned as either a string or {"value": "..."}
            fs = doc.get("first_sentence", "")
            if isinstance(fs, dict):
                summary = fs.get("value", "")
            elif isinstance(fs, str):
                summary = fs

        # --- Cover ---
        cover_id  = doc.get("cover_i")
        cover_url = COVER_URL.format(cover_id=cover_id) if cover_id else ""

        # --- Create book ---
        book = Book.objects.create(
            title=title,
            author=author_obj,
            summary=summary,
            cover_url=cover_url,
        )

        # --- Genres (up to 5 from Open Library subjects) ---
        for subject_name in (doc.get("subject") or [])[:5]:
            if subject_name and len(subject_name) <= 200:
                genre, _ = Genre.objects.get_or_create(name=subject_name)
                book.genre.add(genre)

        safe_title = title.encode("ascii", errors="replace").decode("ascii")
        self.stdout.write(f"  + {safe_title}")
        return True

    def _fetch_description(self, work_key):
        """Fetch the full description for a work from the Open Library Works API."""
        try:
            url = f"https://openlibrary.org{work_key}.json"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            desc = resp.json().get("description", "")
            if isinstance(desc, dict):
                return desc.get("value", "")
            return str(desc) if desc else ""
        except requests.RequestException:
            return ""
