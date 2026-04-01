"""
Management command to create test users + book listings for development.

Usage:
    python manage.py add_test_data          # create test data
    python manage.py add_test_data --clear  # wipe test users first, then recreate
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from catalog.models import Book, BookInstance


TEST_USERS = [
    {
        'username': 'alice_reads',
        'password': 'testpass123',
        'first_name': 'Alice',
        'last_name': 'Nguyen',
        'city': 'Ho Chi Minh City',
        'bio': 'Love sci-fi and fantasy.',
        'credit_balance': 5,
        'books': [
            ('1984', 'l', 'p'),
            ('A Game of Thrones', 'v', 'h'),
            ('The Great Gatsby', 'g', 'p'),
        ],
    },
    {
        'username': 'bob_books',
        'password': 'testpass123',
        'first_name': 'Bob',
        'last_name': 'Tran',
        'city': 'Hanoi',
        'bio': 'Classics collector.',
        'credit_balance': 4,
        'books': [
            ('To Kill a Mockingbird', 'l', 'p'),
            ('Pride and Prejudice', 'v', 'p'),
            ('The Catcher in the Rye', 'g', 'p'),
            ('Brave New World', 'l', 'h'),
        ],
    },
    {
        'username': 'carol_lit',
        'password': 'testpass123',
        'first_name': 'Carol',
        'last_name': 'Le',
        'city': 'Da Nang',
        'bio': 'Historical fiction is my thing.',
        'credit_balance': 6,
        'books': [
            ('Harry Potter and the Sorcerer\'s Stone', 'l', 'h'),
            ('The Lord of the Rings', 'v', 'h'),
            ('A Thousand Splendid Suns', 'l', 'p'),
        ],
    },
    {
        'username': 'dan_pages',
        'password': 'testpass123',
        'first_name': 'Dan',
        'last_name': 'Pham',
        'city': 'Can Tho',
        'bio': 'Reading on the Mekong.',
        'credit_balance': 3,
        'books': [
            ('The Alchemist', 'v', 'p'),
            ('Crime and Punishment', 'g', 'p'),
            ('The Hitchhiker\'s Guide to the Galaxy', 'l', 'p'),
        ],
    },
]


class Command(BaseCommand):
    help = 'Add test users and book listings for development'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Delete existing test users first')

    def handle(self, *args, **options):
        usernames = [u['username'] for u in TEST_USERS]

        if options['clear']:
            deleted, _ = User.objects.filter(username__in=usernames).delete()
            self.stdout.write(self.style.WARNING(f'Deleted {deleted} existing test user(s).'))

        created_users = 0
        created_copies = 0
        skipped_books = []

        for data in TEST_USERS:
            user, created = User.objects.get_or_create(
                username=data['username'],
                defaults={
                    'first_name': data['first_name'],
                    'last_name': data['last_name'],
                    'email': f"{data['username']}@example.com",
                },
            )
            if created:
                user.set_password(data['password'])
                user.save()
                created_users += 1

            # Update profile
            profile = user.profile
            profile.city = data['city']
            profile.bio = data['bio']
            profile.points = data['points']
            profile.credit_balance = data['credit_balance']
            # Save without triggering geocoding (no address set)
            profile.city = data['city']
            profile.save(update_fields=['city', 'bio', 'credit_balance'])

            for title, condition, book_type in data['books']:
                # Flexible match: contains the title string
                book = Book.objects.filter(title__icontains=title).first()
                if not book:
                    skipped_books.append(title)
                    continue

                # Skip if user already has an available copy
                if BookInstance.objects.filter(book=book, user=user, status='a').exists():
                    continue

                BookInstance.objects.create(
                    book=book,
                    user=user,
                    status='a',
                    condition=condition,
                    type=book_type,
                )
                created_copies += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done. Created {created_users} new user(s), {created_copies} book listing(s).'
        ))
        if skipped_books:
            self.stdout.write(self.style.WARNING(
                f'Books not found in DB (skipped): {", ".join(skipped_books)}'
            ))
        self.stdout.write('')
        self.stdout.write('Test accounts:')
        for u in TEST_USERS:
            self.stdout.write(f'  username: {u["username"]}  password: {u["password"]}  city: {u["city"]}')
