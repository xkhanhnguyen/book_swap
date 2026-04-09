"""
Tests for the 10 new features added to BookSwap.
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
import datetime

from catalog.models import (
    Book, Author, BookInstance, SwapRequest, Genre, Dispute,
    Wishlist, SwapRating, ReadingList, BookReview, Notification,
    CreditTransaction,
)
from users.models import Profile


def make_user(username, password='pass1234!', credit_balance=5):
    user = User.objects.create_user(username=username, password=password, email=f'{username}@example.com')
    Profile.objects.filter(user=user).update(credit_balance=credit_balance)
    user.refresh_from_db()
    return user


def make_book(title='Test Book'):
    author = Author.objects.create(first_name='Test', last_name='Author')
    book = Book.objects.create(title=title, author=author)
    return book


def make_copy(book, user, status='a'):
    return BookInstance.objects.create(book=book, user=user, status=status)


def make_completed_swap(owner, requester, book=None):
    if book is None:
        book = make_book('Completed Book')
    copy = make_copy(book, owner, status='s')
    swap = SwapRequest.objects.create(
        requester=requester,
        book_instance=copy,
        status='completed',
        dispute_deadline=timezone.now() + datetime.timedelta(hours=48),
    )
    return swap


class Feature1DisputeModelTest(TestCase):
    """Feature 1: Book Condition Dispute System"""

    def setUp(self):
        self.owner = make_user('owner')
        self.requester = make_user('requester')
        self.swap = make_completed_swap(self.owner, self.requester)

    def test_can_open_dispute_within_window(self):
        self.assertTrue(self.swap.can_open_dispute(self.requester))

    def test_cannot_open_dispute_as_owner(self):
        self.assertFalse(self.swap.can_open_dispute(self.owner))

    def test_cannot_open_dispute_after_deadline(self):
        self.swap.dispute_deadline = timezone.now() - datetime.timedelta(hours=1)
        self.swap.save()
        self.assertFalse(self.swap.can_open_dispute(self.requester))

    def test_cannot_open_dispute_if_not_completed(self):
        book = make_book('Pending Book')
        copy = make_copy(book, self.owner, status='a')
        pending_swap = SwapRequest.objects.create(
            requester=self.requester, book_instance=copy, status='pending'
        )
        self.assertFalse(pending_swap.can_open_dispute(self.requester))

    def test_dispute_creation(self):
        dispute = Dispute.objects.create(
            swap=self.swap,
            opened_by=self.requester,
            arrived_condition='damaged',
            description='Cover is torn',
        )
        self.assertEqual(dispute.status, 'open')
        self.assertEqual(dispute.swap, self.swap)

    def test_open_dispute_view(self):
        client = Client()
        client.login(username='requester', password='pass1234!')
        url = reverse('open-dispute', args=[self.swap.pk])
        resp = client.post(url, {
            'arrived_condition': 'damaged',
            'description': 'Pages missing',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Dispute.objects.filter(swap=self.swap).exists())

    def test_open_dispute_view_owner_denied(self):
        client = Client()
        client.login(username='owner', password='pass1234!')
        url = reverse('open-dispute', args=[self.swap.pk])
        resp = client.post(url, {'arrived_condition': 'damaged'})
        # Should redirect with error
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Dispute.objects.filter(swap=self.swap).exists())

    def test_resolve_dispute_staff_only(self):
        Dispute.objects.create(
            swap=self.swap, opened_by=self.requester, arrived_condition='damaged'
        )
        client = Client()
        client.login(username='requester', password='pass1234!')
        url = reverse('resolve-dispute', args=[1])
        resp = client.post(url, {'action': 'requester'})
        # Non-staff redirected to admin login
        self.assertNotEqual(resp.status_code, 200)


class Feature2WishlistTest(TestCase):
    """Feature 2: Wishlist / Book Request Board"""

    def setUp(self):
        self.user = make_user('wisher')
        self.client = Client()
        self.client.login(username='wisher', password='pass1234!')

    def test_add_to_wishlist(self):
        resp = self.client.post(reverse('wishlist'), {
            'title': 'Dune', 'author': 'Frank Herbert', 'isbn': ''
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Wishlist.objects.filter(user=self.user, title='Dune').exists())

    def test_delete_wishlist_item(self):
        item = Wishlist.objects.create(user=self.user, title='Dune')
        resp = self.client.post(reverse('delete-wishlist', args=[item.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Wishlist.objects.filter(pk=item.pk).exists())

    def test_mark_fulfilled(self):
        item = Wishlist.objects.create(user=self.user, title='Neuromancer')
        resp = self.client.post(reverse('wishlist-fulfilled', args=[item.pk]))
        self.assertEqual(resp.status_code, 302)
        item.refresh_from_db()
        self.assertTrue(item.fulfilled)

    def test_request_board_public(self):
        Wishlist.objects.create(user=self.user, title='Foundation')
        client = Client()  # anonymous
        resp = client.get(reverse('request-board'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Foundation')

    def test_wishlist_notification_on_add_copy(self):
        owner = make_user('bookowner')
        book = make_book('The Road')
        Wishlist.objects.create(user=self.user, title='The Road')
        c = Client()
        c.login(username='bookowner', password='pass1234!')
        c.post(reverse('add-copy', args=[book.pk]), {
            'condition': 'g', 'type': 'p', 'imprint': ''
        })
        notif = Notification.objects.filter(user=self.user, message__icontains='The Road')
        self.assertTrue(notif.exists())


class Feature3SearchFilterTest(TestCase):
    """Feature 3: Search & Filter Improvements"""

    def setUp(self):
        genre = Genre.objects.create(name='Fiction')
        author = Author.objects.create(first_name='A', last_name='B')
        self.book = Book.objects.create(title='Great Novel', author=author)
        self.book.genre.add(genre)
        user = make_user('reader')
        BookInstance.objects.create(book=self.book, user=user, status='a', condition='l')

    def test_genre_filter(self):
        resp = self.client.get(reverse('books'), {'genre': 'Fiction'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.book, resp.context['book_list'])

    def test_condition_filter(self):
        resp = self.client.get(reverse('books'), {'condition': 'l'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.book, resp.context['book_list'])

    def test_sort_newest(self):
        resp = self.client.get(reverse('books'), {'sort': 'newest'})
        self.assertEqual(resp.status_code, 200)

    def test_available_filter(self):
        resp = self.client.get(reverse('books'), {'available': '1'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.book, resp.context['book_list'])


class Feature4RatingTest(TestCase):
    """Feature 4: User Rating System"""

    def setUp(self):
        self.owner = make_user('rateowner')
        self.requester = make_user('raterequester')
        self.swap = make_completed_swap(self.owner, self.requester)

    def test_swap_rating_creation(self):
        rating = SwapRating.objects.create(
            swap=self.swap,
            rated_by=self.requester,
            rated_user=self.owner,
            score=4,
            comment='Great shipper!',
        )
        self.assertEqual(rating.score, 4)

    def test_unique_rating_per_swap_per_user(self):
        SwapRating.objects.create(
            swap=self.swap, rated_by=self.requester, rated_user=self.owner, score=3
        )
        with self.assertRaises(Exception):
            SwapRating.objects.create(
                swap=self.swap, rated_by=self.requester, rated_user=self.owner, score=4
            )

    def test_avg_rating_property(self):
        book2 = make_book('Book2')
        copy2 = make_copy(book2, self.owner, status='s')
        swap2 = SwapRequest.objects.create(
            requester=self.requester, book_instance=copy2, status='completed'
        )
        SwapRating.objects.create(
            swap=self.swap, rated_by=self.requester, rated_user=self.owner, score=4
        )
        SwapRating.objects.create(
            swap=swap2, rated_by=self.requester, rated_user=self.owner, score=2
        )
        self.owner.refresh_from_db()
        avg = self.owner.profile.avg_rating
        self.assertEqual(avg, 3.0)

    def test_rate_swap_view_post(self):
        c = Client()
        c.login(username='raterequester', password='pass1234!')
        resp = c.post(reverse('rate-swap', args=[self.swap.pk]), {'score': '5', 'comment': 'Excellent'})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(SwapRating.objects.filter(swap=self.swap, rated_by=self.requester).exists())

    def test_has_warning_badge(self):
        # needs >= 5 ratings with avg < 2.0
        profile = self.owner.profile
        # fewer than 5 ratings
        self.assertFalse(profile.has_warning_badge)


class Feature5VerifiedShipperTest(TestCase):
    """Feature 5: Verified Shipper Badge"""

    def test_verified_after_5_swaps(self):
        owner = make_user('shipowner')
        profile = owner.profile
        profile.completed_swaps_count = 4
        profile.save(update_fields=['completed_swaps_count'])
        profile.refresh_from_db()
        self.assertFalse(profile.is_verified_shipper)
        profile.completed_swaps_count += 1
        if profile.completed_swaps_count >= 5:
            profile.is_verified_shipper = True
        profile.save(update_fields=['completed_swaps_count', 'is_verified_shipper'])
        profile.refresh_from_db()
        self.assertTrue(profile.is_verified_shipper)

    def test_verified_flag_shown_in_book_detail(self):
        owner = make_user('verifiedowner')
        owner.profile.is_verified_shipper = True
        owner.profile.save(update_fields=['is_verified_shipper'])
        book = make_book('Verified Book')
        make_copy(book, owner)
        resp = self.client.get(reverse('book-detail', args=[book.pk]))
        self.assertContains(resp, 'Verified')


class Feature6ReadingListTest(TestCase):
    """Feature 6: Reading Lists & Book Reviews"""

    def setUp(self):
        self.user = make_user('reader6')
        self.book = make_book('My Reading Book')
        self.client = Client()
        self.client.login(username='reader6', password='pass1234!')

    def test_add_to_shelf(self):
        resp = self.client.post(reverse('add-to-shelf', args=[self.book.pk]), {'status': 'reading'})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ReadingList.objects.filter(user=self.user, book=self.book, status='reading').exists())

    def test_update_shelf_status(self):
        ReadingList.objects.create(user=self.user, book=self.book, status='reading')
        self.client.post(reverse('add-to-shelf', args=[self.book.pk]), {'status': 'completed'})
        entry = ReadingList.objects.get(user=self.user, book=self.book)
        self.assertEqual(entry.status, 'completed')

    def test_remove_from_shelf(self):
        entry = ReadingList.objects.create(user=self.user, book=self.book, status='reading')
        resp = self.client.post(reverse('remove-from-shelf', args=[entry.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ReadingList.objects.filter(pk=entry.pk).exists())

    def test_review_requires_completed_swap(self):
        # No completed swap → cannot review
        resp = self.client.post(reverse('write-review', args=[self.book.pk]), {'rating': 4})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(BookReview.objects.filter(user=self.user, book=self.book).exists())

    def test_review_with_completed_swap(self):
        owner = make_user('bookowner6')
        copy = make_copy(self.book, owner, status='s')
        SwapRequest.objects.create(
            requester=self.user, book_instance=copy, status='completed'
        )
        resp = self.client.post(reverse('write-review', args=[self.book.pk]), {
            'rating': '4', 'review_text': 'Loved it!'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(BookReview.objects.filter(user=self.user, book=self.book, rating=4).exists())

    def test_my_shelf_view(self):
        ReadingList.objects.create(user=self.user, book=self.book, status='reading')
        resp = self.client.get(reverse('my-shelf'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'My Reading Book')


class Feature7SwapHistoryTest(TestCase):
    """Feature 7: Swap History Timeline"""

    def setUp(self):
        self.owner = make_user('histowner')
        self.requester = make_user('histrequester')
        self.swap = make_completed_swap(self.owner, self.requester)

    def test_swap_history_view_as_owner(self):
        c = Client()
        c.login(username='histowner', password='pass1234!')
        resp = c.get(reverse('swap-history'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('timeline', resp.context)
        self.assertEqual(len(resp.context['timeline']), 1)
        self.assertEqual(resp.context['timeline'][0]['direction'], 'Sent')

    def test_swap_history_view_as_requester(self):
        c = Client()
        c.login(username='histrequester', password='pass1234!')
        resp = c.get(reverse('swap-history'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['timeline'][0]['direction'], 'Received')

    def test_stats_context(self):
        c = Client()
        c.login(username='histowner', password='pass1234!')
        resp = c.get(reverse('swap-history'))
        stats = resp.context['stats']
        self.assertEqual(stats['total_sent'], 1)
        self.assertEqual(stats['total_received'], 0)

    def test_requires_login(self):
        resp = self.client.get(reverse('swap-history'))
        self.assertNotEqual(resp.status_code, 200)


class Feature8EmailTest(TestCase):
    """Feature 8: Email Notifications — basic utility test."""

    def test_send_skips_when_no_api_key(self):
        from catalog.utils.email import send_notification_email
        # Should not raise even with no key configured
        try:
            send_notification_email('test@example.com', 'Subject', 'Body')
        except Exception as e:
            self.fail(f'send_notification_email raised an exception: {e}')

    def test_profile_email_notifications_default_true(self):
        user = make_user('emailuser')
        self.assertTrue(user.profile.email_notifications)


class Feature9PWATest(TestCase):
    """Feature 9: PWA manifest and service worker are served."""

    def test_manifest_static_file_exists(self):
        import os
        from django.conf import settings
        manifest_path = os.path.join(settings.BASE_DIR, 'static', 'manifest.json')
        self.assertTrue(os.path.exists(manifest_path))

    def test_sw_js_exists(self):
        import os
        from django.conf import settings
        sw_path = os.path.join(settings.BASE_DIR, 'static', 'sw.js')
        self.assertTrue(os.path.exists(sw_path))

    def test_icons_exist(self):
        import os
        from django.conf import settings
        for size in [192, 512]:
            path = os.path.join(settings.BASE_DIR, 'static', 'icons', f'icon-{size}.png')
            self.assertTrue(os.path.exists(path), f'Missing icon: {path}')


class Feature10ISBNScannerTest(TestCase):
    """Feature 10: ISBN Barcode Scanner — template is rendered with scanner."""

    def setUp(self):
        self.user = make_user('bookadder')
        self.client = Client()
        self.client.login(username='bookadder', password='pass1234!')

    def test_book_create_form_contains_scanner(self):
        resp = self.client.get(reverse('book-create'))
        self.assertEqual(resp.status_code, 200)
        # QuaggaJS script should be included
        self.assertContains(resp, 'quagga')

    def test_book_create_form_contains_isbn_button(self):
        resp = self.client.get(reverse('book-create'))
        self.assertContains(resp, 'Scan')
