from django.db import models
from django.urls import reverse
import uuid
from django.contrib.auth.models import User
import datetime
from datetime import date
from django.db.models.functions import Lower


class Genre(models.Model):
    """Model representing a book genre."""
    name = models.CharField(max_length=200, help_text='Enter a book genre (e.g. Science Fiction)')

    class Meta:
        ordering = [Lower('name')]

    def get_absolute_url(self):
        return reverse('genre-detail', args=[str(self.id)])

    def __str__(self):
        return self.name


class Language(models.Model):
    """Model representing a Language."""
    name = models.CharField(max_length=200,
                            help_text="Enter the book's natural language (e.g. English, French, Japanese etc.)")

    def __str__(self):
        return self.name


class Book(models.Model):
    """Model representing a book (not a specific copy)."""
    title = models.CharField(max_length=200)
    author = models.ForeignKey('Author', on_delete=models.SET_NULL, null=True)
    summary = models.TextField(blank=True, default='', help_text='Enter a brief description of the book')
    cover_url = models.URLField(blank=True, default='')
    popularity_rank = models.IntegerField(null=True, blank=True,
                                          help_text='Rank from Open Library trending (lower = more popular)')
    credit_value = models.IntegerField(default=1, help_text='Credits required to request a swap for this book')
    genre = models.ManyToManyField(Genre, help_text='Select a genre for this book')

    class Meta:
        ordering = [Lower('title')]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('book-detail', args=[str(self.id)])

    def display_genre(self):
        return ', '.join(genre.name for genre in self.genre.all()[:3])
    display_genre.short_description = 'Genre'


class BookInstance(models.Model):
    """Model representing a specific copy of a book."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4,
                          help_text='Unique ID for this particular book across whole library')
    book = models.ForeignKey('Book', on_delete=models.RESTRICT, null=True)
    imprint = models.CharField(max_length=200, blank=True, default='')
    date_posted = models.DateField(("Date"), default=datetime.date.today)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    SWAP_STATUS = (
        ('a', 'Available'),
        ('s', 'Swapped'),
    )
    status = models.CharField(max_length=1, choices=SWAP_STATUS, blank=True, default='m',
                               help_text='Book availability')

    BOOK_CONDITION = (
        ('l', 'Like New'),
        ('v', 'Very Good'),
        ('g', 'Good'),
        ('a', 'Acceptable'),
    )
    condition = models.CharField(max_length=1, choices=BOOK_CONDITION, blank=True, default='m',
                                  help_text='Book Condition')

    BOOK_TYPE = (
        ('h', 'Hardcover'),
        ('p', 'Paperback'),
    )
    type = models.CharField(max_length=1, choices=BOOK_TYPE, blank=True, default='m',
                             help_text='Book type')

    class Meta:
        ordering = ['date_posted']

    def __str__(self):
        return f'{self.id} ({self.book.title})'

    @property
    def days_since_posted(self):
        return bool(self.date_posted and date.today() > self.date_posted)


class SwapRequest(models.Model):
    """A request by one user to swap a specific book copy."""
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
    points_spent  = models.IntegerField(default=10)
    created_at    = models.DateTimeField(auto_now_add=True)

    # Shippo label fields
    label_url         = models.URLField(blank=True, default='')
    label_expires_at  = models.DateTimeField(null=True, blank=True)
    label_downloaded  = models.BooleanField(default=False)
    shipping_cost_usd = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    credits_earned    = models.IntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.requester} → {self.book_instance.book.title} ({self.status})'

    def get_absolute_url(self):
        return reverse('swap-detail', args=[str(self.id)])


class ShippingReceipt(models.Model):
    """Proof of shipping uploaded by a user to earn points."""
    swap_request   = models.ForeignKey(SwapRequest, on_delete=models.CASCADE, related_name='receipts')
    uploaded_by    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='receipts')
    receipt_image  = models.ImageField(upload_to='receipts/')
    points_awarded = models.IntegerField(default=10)
    approved       = models.BooleanField(default=False)
    created_at     = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Receipt by {self.uploaded_by} for {self.swap_request}'


class PointTransaction(models.Model):
    """Audit log for every point change."""
    user        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='point_transactions')
    amount      = models.IntegerField()
    description = models.CharField(max_length=255)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} {self.amount:+d} — {self.description}'


class Notification(models.Model):
    """On-site notification for swap-related events."""
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
    """Model representing an author."""
    first_name    = models.CharField(max_length=100)
    last_name     = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['last_name', Lower('first_name')]

    def get_absolute_url(self):
        return reverse('author-detail', args=[str(self.id)])

    def __str__(self):
        return f'{self.last_name}, {self.first_name}'
