"""
Build (or rebuild) the TF-IDF book recommendation model.

Usage:
    python manage.py build_recommendation_model

The command:
  1. Loads every Book already in the Django database.
  2. Augments the corpus with the Kaggle CSV at settings.BOOKS_DATASET_PATH
     (defaults to <project_root>/book_data.csv).
  3. Deduplicates by (title_lower, author_lower).
  4. Builds a TF-IDF matrix on title + author + genres + description.
  5. Saves the artifacts to settings.RECOMMENDATION_MODEL_PATH
     (defaults to ml_models/book_recommender.pkl).
  6. Prints a short summary and sample recommendations.

Re-running the command always rebuilds from scratch.
"""

import ast
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from catalog.ml.recommender import book_to_text


def _parse_genres(raw):
    """Parse a CSV genres cell like \"['Fiction', 'Fantasy']\" into a string."""
    try:
        result = ast.literal_eval(raw)
        if isinstance(result, list):
            return ' '.join(str(g).strip() for g in result)
    except Exception:
        pass
    return str(raw) if raw and str(raw) != 'nan' else ''


class Command(BaseCommand):
    help = 'Build the TF-IDF book recommendation model from the DB + Kaggle CSV.'

    def handle(self, *args, **options):
        # ── Dependency check ──────────────────────────────────────────────────
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            import joblib
            import pandas as pd
        except ImportError:
            self.stderr.write(
                self.style.ERROR(
                    'Missing dependencies. Run: pip install scikit-learn joblib pandas'
                )
            )
            return

        from catalog.models import Book

        rows = []        # list of {'text': str, 'db_id': int | None}
        seen = set()     # (title_lower, author_lower) — for deduplication

        # ── 1. DB books ───────────────────────────────────────────────────────
        self.stdout.write('Loading books from database...')
        db_books = (
            Book.objects.all()
            .prefetch_related('genre')
            .select_related('author')
        )
        for book in db_books:
            author_name = str(book.author) if book.author else ''
            key = (book.title.lower().strip(), author_name.lower().strip())
            if key in seen:
                continue
            seen.add(key)
            genres = ' '.join(g.name for g in book.genre.all())
            text = book_to_text(book.title, author_name, genres, book.summary)
            rows.append({'text': text, 'db_id': book.pk})

        self.stdout.write(f'  {len(rows)} books loaded from DB.')

        # ── 2. Kaggle CSV ─────────────────────────────────────────────────────
        csv_path = getattr(settings, 'BOOKS_DATASET_PATH', '')
        if not csv_path:
            csv_path = os.path.join(str(settings.BASE_DIR), 'book_data.csv')
        elif not os.path.isabs(csv_path):
            csv_path = os.path.join(str(settings.BASE_DIR), csv_path)

        csv_added = 0
        if os.path.exists(csv_path):
            self.stdout.write(f'Loading CSV from {csv_path}...')
            try:
                df = pd.read_csv(csv_path, on_bad_lines='skip')
                for _, row in df.iterrows():
                    title = str(row.get('title', '')).strip()
                    author = str(row.get('author', '')).strip()
                    if not title or title == 'nan':
                        continue
                    key = (title.lower(), author.lower())
                    if key in seen:
                        continue
                    seen.add(key)

                    genres = _parse_genres(row.get('genres', ''))
                    description = str(row.get('description', ''))
                    if description == 'nan':
                        description = ''
                    text = book_to_text(title, author, genres, description)
                    rows.append({'text': text, 'db_id': None})
                    csv_added += 1

                self.stdout.write(f'  {csv_added} additional books from CSV.')
            except Exception as exc:
                self.stderr.write(f'Warning: could not load CSV ({exc}). Continuing with DB books only.')
        else:
            self.stdout.write(f'CSV not found at {csv_path} — skipping (DB books only).')

        if not rows:
            self.stderr.write(self.style.ERROR('No books to index. Aborting.'))
            return

        # ── 3. Build TF-IDF matrix ────────────────────────────────────────────
        total = len(rows)
        self.stdout.write(f'Building TF-IDF matrix on {total} books...')
        texts = [r['text'] for r in rows]
        db_ids = [r['db_id'] for r in rows]

        vectorizer = TfidfVectorizer(
            max_features=15000,
            stop_words='english',
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
        )
        tfidf_matrix = vectorizer.fit_transform(texts)
        self.stdout.write(f'  Matrix shape: {tfidf_matrix.shape}')

        # ── 4. Save artifacts ─────────────────────────────────────────────────
        model_path = getattr(settings, 'RECOMMENDATION_MODEL_PATH', 'ml_models/book_recommender.pkl')
        if not os.path.isabs(model_path):
            model_path = os.path.join(str(settings.BASE_DIR), model_path)

        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        joblib.dump(
            {'vectorizer': vectorizer, 'tfidf_matrix': tfidf_matrix, 'db_ids': db_ids},
            model_path,
        )
        size_mb = os.path.getsize(model_path) / (1024 * 1024)
        self.stdout.write(f'Model saved to {model_path} ({size_mb:.1f} MB)')

        # ── 5. Sample recommendations ─────────────────────────────────────────
        from sklearn.metrics.pairwise import cosine_similarity
        from catalog.models import BookInstance

        available_book_ids = set(
            BookInstance.objects.filter(status='a').values_list('book_id', flat=True)
        )
        sample = Book.objects.filter(pk__in=available_book_ids).first()
        if sample:
            author_name = str(sample.author) if sample.author else ''
            genres = ' '.join(g.name for g in sample.genre.all())
            qv = vectorizer.transform([book_to_text(sample.title, author_name, genres, sample.summary)])
            sims = cosine_similarity(qv, tfidf_matrix)[0]
            candidates = [
                (db_ids[i], sims[i])
                for i in range(len(sims))
                if db_ids[i] is not None
                and db_ids[i] in available_book_ids
                and db_ids[i] != sample.pk
            ]
            candidates.sort(key=lambda x: x[1], reverse=True)
            top_books = list(
                Book.objects.filter(pk__in=[c[0] for c in candidates[:3]])
            )
            self.stdout.write(f"\nSample: '{sample.title}'")
            for b in top_books:
                self.stdout.write(f'  - {b.title}')

        db_indexed = sum(1 for d in db_ids if d is not None)
        self.stdout.write(
            self.style.SUCCESS(
                f'\nDone! {db_indexed} DB books + {csv_added} CSV-only books indexed.'
            )
        )
