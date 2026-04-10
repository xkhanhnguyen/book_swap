"""
Book Recommendation Engine (TF-IDF based).

Usage:
    from catalog.ml.recommender import get_engine

    engine = get_engine()
    books = engine.get_recommendations(book_instance, n=5, exclude_user=request.user)

The engine is a module-level lazy singleton — the .pkl file is loaded once on
first access and reused for all subsequent requests.  If the model file does
not exist yet (i.e. build_recommendation_model hasn't been run), every call
returns an empty list and a warning is logged; the rest of the app is unaffected.
"""

import logging
import os

logger = logging.getLogger(__name__)

_engine = None


def get_engine():
    """Return the shared RecommendationEngine, loading it on first call."""
    global _engine
    if _engine is None:
        _engine = RecommendationEngine()
    return _engine


def book_to_text(title, author_name, genre_names, summary):
    """Combine book fields into a single text blob for TF-IDF vectorisation."""
    parts = [title]
    if author_name:
        parts.append(author_name)
    if genre_names:
        parts.append(genre_names)
    if summary:
        parts.append(summary[:500])
    return ' '.join(filter(None, parts))


class RecommendationEngine:
    def __init__(self):
        self._loaded = False
        self._tfidf_matrix = None
        self._vectorizer = None
        self._db_ids = None   # list[int | None] — None for CSV-only rows
        self._load()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _model_path(self):
        from django.conf import settings
        path = getattr(settings, 'RECOMMENDATION_MODEL_PATH', 'ml_models/book_recommender.pkl')
        if not os.path.isabs(path):
            path = os.path.join(str(settings.BASE_DIR), path)
        return path

    def _load(self):
        try:
            import joblib
            path = self._model_path()
            if not os.path.exists(path):
                logger.warning(
                    "Recommendation model not found at %s. "
                    "Run: python manage.py build_recommendation_model",
                    path,
                )
                return
            data = joblib.load(path)
            self._vectorizer = data['vectorizer']
            self._tfidf_matrix = data['tfidf_matrix']
            self._db_ids = data['db_ids']
            self._loaded = True
            logger.info("Recommendation model loaded from %s", path)
        except Exception as exc:
            logger.warning("Failed to load recommendation model: %s", exc)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_recommendations(self, book, user, n=5):
        """
        Return up to *n* Book instances similar to *book* that currently have
        an available copy for swap, with all user-specific books excluded.

        Excluded books:
        - The seed book itself
        - Any book the user has listed (BookInstance.user == user), any status
        - Any book the user has ever requested a swap for (any status:
          pending, accepted, rejected, completed) — covers received books,
          declined requests, and in-flight swaps

        Parameters
        ----------
        book : catalog.models.Book
        user : django.contrib.auth.models.User
        n    : int
        """
        if not self._loaded:
            return []
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            from catalog.models import BookInstance, SwapRequest, Book

            # Books the user owns (has listed), regardless of status
            owned_book_ids = set(
                BookInstance.objects
                .filter(user=user)
                .values_list('book_id', flat=True)
            )

            # Books the user has ever requested (any status: pending, accepted,
            # rejected, completed) — covers received, declined, and in-flight
            requested_book_ids = set(
                SwapRequest.objects
                .filter(requester=user)
                .values_list('book_instance__book_id', flat=True)
            )

            exclude_ids = owned_book_ids | requested_book_ids | {book.pk}

            # Available copies not belonging to the user and not in exclude set
            available_book_ids = set(
                BookInstance.objects
                .filter(status='a')
                .exclude(user=user)
                .values_list('book_id', flat=True)
            ) - exclude_ids

            if not available_book_ids:
                return []

            # Vectorise the query book
            genres = ' '.join(g.name for g in book.genre.all())
            author_name = str(book.author) if book.author else ''
            query_text = book_to_text(book.title, author_name, genres, book.summary)
            query_vec = self._vectorizer.transform([query_text])

            # Cosine similarity against the full index
            sims = cosine_similarity(query_vec, self._tfidf_matrix)[0]

            # Keep only rows that map to an available DB book
            db_ids = self._db_ids
            results = [
                (db_ids[i], float(sims[i]))
                for i in range(len(sims))
                if db_ids[i] is not None and db_ids[i] in available_book_ids
            ]
            results.sort(key=lambda x: x[1], reverse=True)
            top_ids = [pk for pk, _ in results[:n]]

            if not top_ids:
                return []

            books_by_id = {
                b.pk: b
                for b in Book.objects.filter(pk__in=top_ids).select_related('author')
            }
            return [books_by_id[pk] for pk in top_ids if pk in books_by_id]

        except Exception as exc:
            logger.warning("Recommendation inference failed: %s", exc)
            return []
