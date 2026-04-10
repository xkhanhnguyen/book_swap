from django.db import models
from django.urls import reverse
import uuid
from django.contrib.auth.models import User
import datetime
from datetime import date
from django.db.models.functions import Lower
from django.utils import timezone


class Genre(models.Model):
    name = models.CharField(max_length=200, help_text='Enter a book genre (e.g. Science Fiction)')

    class Meta:
        ordering = [Lower('name')]

    def get_absolute_url(self):
        return reverse('genre-detail', args=[str(self.id)])

    def __str__(self):
        return self.name


class Language(models.Model):
    name = models.CharField(max_length=200,
                            help_text="Enter the book's natural language (e.g. English, French, Japanese etc.)")

    def __str__(self):
        return self.name


class Book(models.Model):
    title        = models.CharField(max_length=200)
    author       = models.ForeignKey('Author', on_delete=models.SET_NULL, null=True)
    summary      = models.TextField(blank=True, default='')
    cover_url    = models.URLField(blank=True, default='')
    popularity_rank = models.IntegerField(null=True, blank=True)
    credit_value = models.IntegerField(default=1,
                                       help_text='Credits required to request a swap for this book')
    genre        = models.ManyToManyField(Genre)

    class Meta:
        ordering = [Lower('title')]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('book-detail', args=[str(self.id)])

    def display_genre(self):
        return ', '.join(genre.name for genre in self.genre.all()[:3])
    display_genre.short_description = 'Genre'

    @property
    def avg_review_rating(self):
        reviews = self.reviews.all()
        if not reviews.exists():
            return None
        return round(reviews.aggregate(avg=models.Avg('rating'))['avg'], 1)

    @property
    def total_reviews(self):
        return self.reviews.count()


class BookInstance(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4)
    book       = models.ForeignKey('Book', on_delete=models.RESTRICT, null=True)
    imprint    = models.CharField(max_length=200, blank=True, default='')
    date_posted = models.DateField(default=datetime.date.today)
    user       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    SWAP_STATUS = (('a', 'Available'), ('s', 'Swapped'))
    status = models.CharField(max_length=1, choices=SWAP_STATUS, blank=True, default='m')

    BOOK_CONDITION = (('l', 'Like New'), ('v', 'Very Good'), ('g', 'Good'), ('a', 'Acceptable'))
    condition = models.CharField(max_length=1, choices=BOOK_CONDITION, blank=True, default='m')

    BOOK_TYPE = (('h', 'Hardcover'), ('p', 'Paperback'))
    type = models.CharField(max_length=1, choices=BOOK_TYPE, blank=True, default='m')

    cover_photo = models.ImageField(upload_to='book_photos/', blank=True, null=True)

    class Meta:
        ordering = ['date_posted']

    def __str__(self):
        return f'{self.id} ({self.book.title})'

    @property
    def days_since_posted(self):
        return bool(self.date_posted and date.today() > self.date_posted)


ARRIVED_CONDITION_CHOICES = [
    ('as_described', 'As Described'),
    ('worse_than_described', 'Worse Than Described'),
    ('damaged', 'Damaged'),
]


class SwapRequest(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('accepted',  'Accepted'),
        ('rejected',  'Rejected'),
        ('completed', 'Completed'),
    ]
    requester     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='swap_requests_sent')
    book_instance = models.ForeignKey(BookInstance, on_delete=models.CASCADE, related_name='swap_requests')
    status        = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    message       = models.TextField(blank=True, default='')
    created_at    = models.DateTimeField(auto_now_add=True)

    # Shippo label fields
    label_url        = models.URLField(blank=True, default='')
    label_expires_at = models.DateTimeField(null=True, blank=True)
    label_downloaded = models.BooleanField(default=False)
    shipping_cost_usd = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    credits_earned   = models.IntegerField(default=0)

    # Feature 1: condition dispute
    arrived_condition = models.CharField(
        max_length=25, choices=ARRIVED_CONDITION_CHOICES, blank=True, default=''
    )
    dispute_deadline = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.requester} → {self.book_instance.book.title} ({self.status})'

    def get_absolute_url(self):
        return reverse('swap-detail', args=[str(self.id)])

    def can_open_dispute(self, user):
        """True if user is the requester, swap is completed, and within the dispute window."""
        if self.status != 'completed':
            return False
        if self.requester != user:
            return False
        if not self.dispute_deadline:
            return False
        return timezone.now() <= self.dispute_deadline


class Dispute(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('resolved_for_requester', 'Resolved for Requester'),
        ('resolved_for_owner', 'Resolved for Owner'),
    ]
    swap = models.OneToOneField(SwapRequest, on_delete=models.CASCADE, related_name='dispute')
    opened_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='disputes_opened')
    arrived_condition = models.CharField(max_length=25, choices=ARRIVED_CONDITION_CHOICES)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='open')
    credits_frozen = models.IntegerField(default=0)
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='disputes_resolved'
    )

    def __str__(self):
        return f'Dispute #{self.pk} for Swap #{self.swap_id} ({self.status})'


class ShippingReceipt(models.Model):
    swap_request  = models.ForeignKey(SwapRequest, on_delete=models.CASCADE, related_name='receipts')
    uploaded_by   = models.ForeignKey(User, on_delete=models.CASCADE, related_name='receipts')
    receipt_image = models.ImageField(upload_to='receipts/')
    approved      = models.BooleanField(default=False)
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Receipt by {self.uploaded_by} for {self.swap_request}'


class CreditTransaction(models.Model):
    """Audit log for every credit change."""
    user        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='credit_transactions')
    amount      = models.IntegerField()   # positive = earned, negative = spent
    description = models.CharField(max_length=255)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} {self.amount:+d} cr — {self.description}'


class Notification(models.Model):
    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message      = models.CharField(max_length=500)
    read         = models.BooleanField(default=False)
    swap_request = models.ForeignKey(SwapRequest, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='notifications')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Notification for {self.user}: {self.message[:50]}'


class Author(models.Model):
    first_name    = models.CharField(max_length=100)
    last_name     = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['last_name', Lower('first_name')]

    def get_absolute_url(self):
        return reverse('author-detail', args=[str(self.id)])

    def __str__(self):
        return f'{self.last_name}, {self.first_name}'


# ─── Feature 2: Wishlist ──────────────────────────────────────────────────────

class Wishlist(models.Model):
    user      = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlist')
    title     = models.CharField(max_length=200)
    author    = models.CharField(max_length=200, blank=True)
    isbn      = models.CharField(max_length=20, blank=True)
    fulfilled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} wants "{self.title}"'


# ─── Feature 4: User Rating System ───────────────────────────────────────────

class SwapRating(models.Model):
    swap       = models.ForeignKey(SwapRequest, on_delete=models.CASCADE, related_name='ratings')
    rated_by   = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ratings_given')
    rated_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ratings_received')
    score      = models.IntegerField()   # 1-5
    comment    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('swap', 'rated_by')]

    def __str__(self):
        return f'{self.rated_by} rated {self.rated_user} {self.score}/5 for swap #{self.swap_id}'


# ─── Feature 6: Reading Lists & Book Reviews ─────────────────────────────────

class ReadingList(models.Model):
    STATUS_CHOICES = [
        ('reading', 'Reading'),
        ('completed', 'Completed'),
        ('want_to_read', 'Want to Read'),
    ]
    user    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reading_list')
    book    = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='reading_lists')
    status  = models.CharField(max_length=20, choices=STATUS_CHOICES)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('user', 'book')]
        ordering = ['-added_at']

    def __str__(self):
        return f'{self.user} — {self.book.title} ({self.status})'


# ─── Analytics: Zip Code Geocode Cache ───────────────────────────────────────

class ZipCodeCache(models.Model):
    """Cache geocoded lat/lng for zip codes to avoid repeated Nominatim calls."""
    zip_code  = models.CharField(max_length=20, unique=True)
    latitude  = models.FloatField()
    longitude = models.FloatField()
    cached_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.zip_code} ({self.latitude}, {self.longitude})'


class BookReview(models.Model):
    user        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    book        = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='reviews')
    rating      = models.IntegerField()   # 1-5
    review_text = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('user', 'book')]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} reviewed "{self.book.title}" ({self.rating}/5)'

    def stars_display(self):
        return '★' * self.rating + '☆' * (5 - self.rating)
