"""
Import books from the Best Books Ever CSV (52k books from Kaggle).
Books are ranked by bbeScore (Best Books Ever popularity score).

Usage:
    python manage.py import_books
    python manage.py import_books --limit 500
    python manage.py import_books --limit 1000 --clear

CSV file expected at: <project_root>/book_data.csv
"""

import csv
import ast
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from catalog.models import Book, Author, Genre

CSV_PATH = os.path.join(settings.BASE_DIR, 'book_data.csv')
COVER_BY_ISBN = "https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg"
COVER_BY_TITLE = "https://covers.openlibrary.org/b/olid/{olid}-M.jpg"


def parse_list_field(value):
    """Parse a string like \"['Genre1', 'Genre2']\" into a Python list."""
    try:
        result = ast.literal_eval(value)
        if isinstance(result, list):
            return [str(i).strip() for i in result]
    except Exception:
        pass
    return []


def clean_isbn(raw):
    """Normalize ISBN from scientific notation or plain string."""
    try:
        # e.g. "9.78044E+12" -> 9780441172719
        return str(int(float(raw))).zfill(13)
    except Exception:
        return raw.strip()


class Command(BaseCommand):
    help = "Import books from book_data.csv ordered by Best Books Ever score"

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=200,
            help='Number of top books to import (default: 200)',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing books before importing',
        )

    def handle(self, *args, **options):
        if not os.path.exists(CSV_PATH):
            self.stdout.write(self.style.ERROR(f"CSV not found at {CSV_PATH}"))
            return

        if options['clear']:
            self.stdout.write("Clearing existing books...")
            Book.objects.all().delete()
            Author.objects.all().delete()
            Genre.objects.all().delete()
            self.stdout.write(self.style.WARNING("Database cleared."))

        limit = options['limit']

        self.stdout.write(f"Reading CSV...")
        with open(CSV_PATH, encoding='utf-8') as f:
            rows = list(csv.DictReader(f))

        # Sort by bbeScore descending (higher = more popular)
        rows.sort(key=lambda r: float(r['bbeScore']) if r['bbeScore'] else 0, reverse=True)
        rows = rows[:limit]

        self.stdout.write(f"Importing top {len(rows)} books by Best Books Ever score...")
        imported = 0
        skipped = 0

        for rank, row in enumerate(rows, start=1):
            title = row.get('title', '').strip()
            if not title:
                continue

            # Author
            author_obj = None
            full_name = row.get('author', '').strip()
            if full_name:
                parts = full_name.rsplit(' ', 1)
                first_name = parts[0] if len(parts) > 1 else full_name
                last_name = parts[1] if len(parts) > 1 else ''
                author_obj, _ = Author.objects.get_or_create(
                    first_name=first_name,
                    last_name=last_name,
                )

            # Skip duplicates
            if Book.objects.filter(title=title, author=author_obj).exists():
                skipped += 1
                continue

            # Description
            summary = row.get('description', '').strip()

            # Cover via ISBN
            isbn = clean_isbn(row.get('isbn', ''))
            cover_url = COVER_BY_ISBN.format(isbn=isbn) if isbn else ''

            # Create book
            book = Book.objects.create(
                title=title,
                author=author_obj,
                summary=summary,
                cover_url=cover_url,
                popularity_rank=rank,
            )

            # Genres
            genres = parse_list_field(row.get('genres', ''))
            for genre_name in genres[:5]:
                if genre_name and len(genre_name) <= 100:
                    g, _ = Genre.objects.get_or_create(name=genre_name)
                    book.genre.add(g)

            imported += 1
            safe_title = title.encode('ascii', errors='replace').decode('ascii')
            self.stdout.write(f"  [{rank:4}] {safe_title}")

        self.stdout.write(
            self.style.SUCCESS(f"\nDone. {imported} imported, {skipped} skipped (already exist).")
        )
