from django.db import models
from django.urls import reverse # Used to generate URLs by reversing the URL patterns
import uuid # Required for unique book instances
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
        """Returns the URL to access a particular genre instance."""
        return reverse('genre-detail', args=[str(self.id)])

    def __str__(self):
        """String for representing the Model object."""
        return self.name



class Language(models.Model):
    """Model representing a Language (e.g. English, French, Japanese, etc.)"""
    name = models.CharField(max_length=200,
                            help_text="Enter the book's natural language (e.g. English, French, Japanese etc.)")

    def __str__(self):
        """String for representing the Model object (in Admin site etc.)"""
        return self.name



class Book(models.Model):
    """Model representing a book (but not a specific copy of a book)."""
    title = models.CharField(max_length=200)

    # Foreign Key used because book can only have one author, but authors can have multiple books
    # Author is a string rather than an object because it hasn't been declared yet in the file
    author = models.ForeignKey('Author', on_delete=models.SET_NULL, null=True)

    summary = models.TextField(blank=True, default='', help_text='Enter a brief description of the book')

    cover_url = models.URLField(blank=True, default='')
    popularity_rank = models.IntegerField(null=True, blank=True, help_text='Rank from Open Library trending (lower = more popular)')

    # ManyToManyField used because genre can contain many books. Books can cover many genres.
    # Genre class has already been defined so we can specify the object above.
    genre = models.ManyToManyField(Genre, help_text='Select a genre for this book')

    class Meta:
        ordering = [Lower('title')]

    def __str__(self):
        """String for representing the Model object."""
        return self.title

    def get_absolute_url(self):
        """Returns the URL to access a detail record for this book."""
        return reverse('book-detail', args=[str(self.id)])
    
    def display_genre(self):
        """Create a string for the Genre. This is required to display genre in Admin."""
        return ', '.join(genre.name for genre in self.genre.all()[:3])

    display_genre.short_description = 'Genre'



class BookInstance(models.Model):
    """Model representing a specific copy of a book (i.e. that can be borrowed from the library)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, help_text='Unique ID for this particular book across whole library')
    book = models.ForeignKey('Book', on_delete=models.RESTRICT, null=True)
    imprint = models.CharField(max_length=200, blank=True, default='')
    date_posted = models.DateField(("Date"), default=datetime.date.today)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    SWAP_STATUS = (
        ('a', 'Available'),
        ('s', 'Swapped'),
    )

    status = models.CharField(
        max_length=1,
        choices=SWAP_STATUS,
        blank=True,
        default='m',
        help_text='Book availability',
    )

    BOOK_CONDITION = (
        ('l', 'Like New'),
        ('v', 'Very Good'),
        ('g', 'Good'),
        ('a', 'Acceptable'),
    )

    condition = models.CharField(
        max_length=1,
        choices=BOOK_CONDITION,
        blank=True,
        default='m',
        help_text='Book Condition',
    )

    BOOK_TYPE = (
        ('h', 'Hardcover'),
        ('p', 'Paperback'),
    )

    type = models.CharField(
        max_length=1,
        choices=BOOK_TYPE,
        blank=True,
        default='m',
        help_text='Book type',
    )

    class Meta:
        ordering = ['date_posted']
        # permissions = (("can_mark_swapped", "Set book as shipped"),)

    def __str__(self):
        """String for representing the Model object."""
        return f'{self.id} ({self.book.title})'
    
    @property
    def days_since_posted(self):
        """Determines how many days since the book posted based on posted date and current date."""
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
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='point_transactions')
    amount     = models.IntegerField()   # positive = earned, negative = spent
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} {self.amount:+d} — {self.description}'


class Author(models.Model):
    """Model representing an author."""
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    # date_of_death = models.DateField('Died', null=True, blank=True)

    class Meta:
        ordering = ['last_name', Lower('first_name')]

    def get_absolute_url(self):
        """Returns the URL to access a particular author instance."""
        return reverse('author-detail', args=[str(self.id)])

    def __str__(self):
        """String for representing the Model object."""
        return f'{self.last_name}, {self.first_name}'
