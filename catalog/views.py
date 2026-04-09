from django.shortcuts import render, redirect
from django.views import generic
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q, Value, Avg
from django.db.models.functions import Concat
import datetime
import math

from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.utils import timezone
from django.contrib import messages
from extra_views import CreateWithInlinesView, InlineFormSetFactory

from .models import (
    Book, Author, BookInstance, Genre, SwapRequest, ShippingReceipt,
    CreditTransaction, Notification, Dispute, Wishlist, SwapRating,
    ReadingList, BookReview,
)
from catalog.forms import RenewBookForm, AddCopyForm
from catalog.utils.email import send_notification_email


# ─── Utilities ───────────────────────────────────────────────────────────────

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
    return R * 2 * math.asin(math.sqrt(a))


# ─── General views ────────────────────────────────────────────────────────────

def index(request):
    num_books = Book.objects.all().count()
    num_instances = BookInstance.objects.all().count()
    num_genre = Genre.objects.all().count()
    num_instances_available = BookInstance.objects.filter(status__exact='a').count()
    num_authors = Author.objects.count()
    num_visits = request.session.get('num_visits', 0)
    request.session['num_visits'] = num_visits + 1

    context = {
        'num_books': num_books,
        'num_instances': num_instances,
        'num_instances_available': num_instances_available,
        'num_authors': num_authors,
        'num_genre': num_genre,
        'num_visits': num_visits,
    }
    return render(request, 'index.html', context=context)


# ─── Book views ───────────────────────────────────────────────────────────────

class BookListView(generic.ListView):
    model = Book
    paginate_by = 20
    context_object_name = 'book_list'

    def get_queryset(self):
        from django.db.models import Count
        qs = Book.objects.annotate(
            available_copies=Count('bookinstance', filter=Q(bookinstance__status='a'))
        )

        # Feature 3: genre filter
        genre_filter = self.request.GET.get('genre', '').strip()
        if genre_filter:
            qs = qs.filter(genre__name__iexact=genre_filter)

        # Feature 3: condition filter (filter by at least one BookInstance with that condition)
        condition_filter = self.request.GET.get('condition', '').strip()
        if condition_filter:
            qs = qs.filter(bookinstance__condition=condition_filter, bookinstance__status='a')

        # availability filter
        if self.request.GET.get('available'):
            qs = qs.filter(available_copies__gt=0)

        # Feature 3: sort
        sort = self.request.GET.get('sort', '')
        if sort == 'newest':
            qs = qs.order_by('-bookinstance__date_posted', 'title')
        elif sort == 'popular':
            qs = qs.order_by('popularity_rank', 'title')
        elif sort == 'closest' and self.request.user.is_authenticated:
            qs = qs.order_by('popularity_rank', 'title')
        else:
            qs = qs.order_by('popularity_rank', 'title')

        return qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['genres'] = Genre.objects.all()
        context['conditions'] = BookInstance.BOOK_CONDITION
        context['current_genre'] = self.request.GET.get('genre', '')
        context['current_condition'] = self.request.GET.get('condition', '')
        context['current_sort'] = self.request.GET.get('sort', '')
        return context


class BookDetailView(generic.DetailView):
    model = Book

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        copies = (
            BookInstance.objects
            .filter(book=self.object, status='a')
            .select_related('user__profile')
        )
        user = self.request.user
        user_lat = user_lon = None
        if user.is_authenticated:
            try:
                user_lat = user.profile.latitude
                user_lon = user.profile.longitude
            except Exception:
                pass

        offers = []
        for copy in copies:
            dist = None
            try:
                olat = copy.user.profile.latitude
                olon = copy.user.profile.longitude
                if user_lat and olat:
                    dist = haversine_km(user_lat, user_lon, olat, olon)
            except Exception:
                pass
            offers.append({'copy': copy, 'distance_km': dist})

        offers.sort(key=lambda x: (x['distance_km'] is None, x['distance_km'] or 0))
        context['swap_offers'] = offers

        # Feature 6: reviews
        context['reviews'] = self.object.reviews.select_related('user__profile').all()

        # Feature 6: reading list status for this user
        shelf_status = None
        shelf_entry = None
        can_review = False
        if user.is_authenticated:
            try:
                shelf_entry = ReadingList.objects.get(user=user, book=self.object)
                shelf_status = shelf_entry.status
            except ReadingList.DoesNotExist:
                pass

            # user can review if they received this book via a completed swap
            can_review = SwapRequest.objects.filter(
                requester=user,
                book_instance__book=self.object,
                status='completed',
            ).exists()
            # check if already reviewed
            already_reviewed = BookReview.objects.filter(user=user, book=self.object).exists()
            context['can_review'] = can_review and not already_reviewed
        context['shelf_entry'] = shelf_entry
        context['shelf_status'] = shelf_status
        context['reading_list_choices'] = ReadingList.STATUS_CHOICES
        return context


class AuthorListView(generic.ListView):
    model = Author
    paginate_by = 20

    def get_queryset(self):
        from django.db.models import Min
        return (
            Author.objects
            .filter(book__isnull=False)
            .annotate(best_rank=Min('book__popularity_rank'))
            .order_by('best_rank', 'last_name')
            .distinct()
        )


class AuthorDetailView(generic.DetailView):
    model = Author


class GenreListView(generic.ListView):
    model = Genre
    paginate_by = 10


class GenreDetailView(generic.DetailView):
    model = Genre


class BooksByUserListView(LoginRequiredMixin, generic.ListView):
    model = BookInstance
    template_name = 'catalog/bookinstance_list_by_user.html'
    paginate_by = 20

    def get_queryset(self):
        return (
            BookInstance.objects.filter(user=self.request.user)
            .select_related('book')
            .order_by('-date_posted')
        )


class BooksByAllListView(LoginRequiredMixin, generic.ListView):
    model = BookInstance
    template_name = 'catalog/bookinstance_list_by_user.html'
    paginate_by = 10

    def get_queryset(self):
        return BookInstance.objects.order_by('date_posted')


@login_required
@permission_required('catalog.can_mark_swapped', raise_exception=True)
def renew_book_librarian(request, pk):
    book_instance = get_object_or_404(BookInstance, pk=pk)
    if request.method == 'POST':
        form = RenewBookForm(request.POST)
        if form.is_valid():
            book_instance.due_back = form.cleaned_data['renewal_date']
            book_instance.save()
            return HttpResponseRedirect(reverse('all-books'))
    else:
        proposed_renewal_date = datetime.date.today() + datetime.timedelta(weeks=3)
        form = RenewBookForm(initial={'renewal_date': proposed_renewal_date})
    return render(request, 'catalog/book_renew_librarian.html', {'form': form, 'book_instance': book_instance})


# ─── Author CRUD ──────────────────────────────────────────────────────────────

class AuthorCreate(InlineFormSetFactory):
    model = Author
    fields = ['first_name', 'last_name', 'date_of_birth']


class AuthorUpdate(UpdateView):
    model = Author
    fields = '__all__'


class AuthorDelete(DeleteView):
    model = Author
    success_url = reverse_lazy('authors')


# ─── Book CRUD ────────────────────────────────────────────────────────────────

class BookCreateView(LoginRequiredMixin, CreateWithInlinesView):
    model = Book
    inclines = [Author]
    fields = ['title', 'author', 'summary', 'genre']
    template_name = 'catalog/book_form.html'

    def get_success_url(self):
        messages.success(self.request, 'Your book-swap has been created successfully.')
        return self.object.get_absolute_url()


class BookUpdateView(LoginRequiredMixin, UpdateView):
    model = Book
    fields = ['title', 'author', 'summary', 'genre']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['update'] = True
        return context

    def get_success_url(self):
        messages.success(self.request, 'Your book has been updated successfully.')
        return reverse_lazy('book')

    def get_queryset(self):
        return self.model.objects.filter(author=self.request.user)


class BookDeleteView(LoginRequiredMixin, DeleteView):
    model = Book

    def get_success_url(self):
        messages.success(self.request, 'Your post has been deleted successfully.')
        return reverse_lazy('book')

    def get_queryset(self):
        return self.model.objects.filter(author=self.request.user)


# ─── Copy management ─────────────────────────────────────────────────────────

@login_required
def add_copy(request, book_pk):
    book = get_object_or_404(Book, pk=book_pk)

    if BookInstance.objects.filter(book=book, user=request.user, status='a').exists():
        messages.warning(request, "You already have an available copy of this book listed.")
        return redirect('book-detail', pk=book_pk)

    if request.method == 'POST':
        form = AddCopyForm(request.POST)
        if form.is_valid():
            copy = form.save(commit=False)
            copy.book = book
            copy.user = request.user
            copy.status = 'a'
            copy.save()

            # Feature 2: notify wishlist users
            wishers = Wishlist.objects.filter(
                title__iexact=book.title, fulfilled=False
            ).exclude(user=request.user).select_related('user__profile')
            for wish in wishers:
                Notification.objects.create(
                    user=wish.user,
                    message=f'A copy of "{book.title}" you wished for is now available for swap!',
                )
                if wish.user.profile.email_notifications:
                    send_notification_email(
                        wish.user.email,
                        f'BookSwap: "{book.title}" is now available',
                        f'Good news! A copy of "{book.title}" that you wished for is now listed for swap on BookSwap.',
                    )

            messages.success(request, f'Your copy of "{book.title}" is now listed for swap.')
            return redirect('book-detail', pk=book_pk)
    else:
        form = AddCopyForm()

    return render(request, 'catalog/add_copy.html', {'book': book, 'form': form})


# ─── Swap flow ───────────────────────────────────────────────────────────────

@login_required
def request_swap(request, pk):
    book_instance = get_object_or_404(BookInstance, pk=pk, status='a')

    if book_instance.user == request.user:
        messages.error(request, "You can't swap your own book.")
        return redirect('book-detail', pk=book_instance.book.pk)

    profile = request.user.profile

    if profile.credit_balance < 1:
        messages.error(request, "You need at least 1 credit to request a swap. Earn credits by shipping books.")
        return redirect('book-detail', pk=book_instance.book.pk)

    if SwapRequest.objects.filter(requester=request.user, book_instance=book_instance, status='pending').exists():
        messages.warning(request, "You already have a pending request for this copy.")
        return redirect('book-detail', pk=book_instance.book.pk)

    if request.method == 'POST':
        message = request.POST.get('message', '')
        swap = SwapRequest.objects.create(
            requester=request.user,
            book_instance=book_instance,
            message=message,
        )
        profile.credit_balance -= 1
        profile.save(update_fields=['credit_balance'])

        CreditTransaction.objects.create(
            user=request.user,
            amount=-1,
            description=f'Requested swap for "{book_instance.book.title}"',
        )

        owner = book_instance.user
        Notification.objects.create(
            user=owner,
            swap_request=swap,
            message=(
                f'{request.user.profile.display_name} requested your copy of '
                f'"{book_instance.book.title}".'
            ),
        )
        # Feature 8: email owner
        if owner.profile.email_notifications:
            send_notification_email(
                owner.email,
                f'BookSwap: Someone requested your book "{book_instance.book.title}"',
                f'Someone requested your copy of "{book_instance.book.title}" on BookSwap. '
                f'Log in to accept or reject the request.',
            )

        messages.success(request, 'Swap request sent! The owner will be notified.')
        return redirect('swap-detail', pk=swap.pk)

    return render(request, 'catalog/swap_request_form.html', {'book_instance': book_instance})


@login_required
def swap_detail(request, pk):
    swap = get_object_or_404(SwapRequest, pk=pk)
    is_owner = swap.book_instance.user == request.user
    is_requester = swap.requester == request.user
    if not (is_owner or is_requester):
        messages.error(request, "You don't have access to this swap.")
        return redirect('books')

    if request.method == 'POST' and is_owner:
        action = request.POST.get('action')
        if action == 'accept' and swap.status == 'pending':
            swap.status = 'accepted'
            swap.save()
            Notification.objects.create(
                user=swap.requester,
                swap_request=swap,
                message=(
                    f'Your swap request for "{swap.book_instance.book.title}" was accepted! '
                    f'Please ship your book.'
                ),
            )
            # Feature 8
            if swap.requester.profile.email_notifications:
                send_notification_email(
                    swap.requester.email,
                    f'BookSwap: Your swap request was accepted',
                    f'Your swap request for "{swap.book_instance.book.title}" was accepted! '
                    f'Please arrange shipping.',
                )
            messages.success(request, 'Swap accepted! Both parties should ship their books.')
        elif action == 'reject' and swap.status == 'pending':
            swap.status = 'rejected'
            swap.save()
            swap.requester.profile.credit_balance += 1
            swap.requester.profile.save(update_fields=['credit_balance'])
            CreditTransaction.objects.create(
                user=swap.requester,
                amount=1,
                description=f'Refund — swap rejected for "{swap.book_instance.book.title}"',
            )
            Notification.objects.create(
                user=swap.requester,
                swap_request=swap,
                message=(
                    f'Your swap request for "{swap.book_instance.book.title}" was rejected. '
                    f'1 credit refunded.'
                ),
            )
            # Feature 8
            if swap.requester.profile.email_notifications:
                send_notification_email(
                    swap.requester.email,
                    f'BookSwap: Your swap request was declined',
                    f'Your swap request for "{swap.book_instance.book.title}" was declined. '
                    f'1 credit has been refunded to your account.',
                )
            messages.info(request, 'Swap rejected. 1 credit refunded to requester.')

    receipts = swap.receipts.all()
    user_has_receipt = receipts.filter(uploaded_by=request.user).exists()
    label_expired = False
    if swap.label_expires_at:
        label_expired = timezone.now() > swap.label_expires_at

    # Feature 1: dispute info
    dispute = None
    can_open_dispute = False
    try:
        dispute = swap.dispute
    except Dispute.DoesNotExist:
        pass
    if dispute is None:
        can_open_dispute = swap.can_open_dispute(request.user)

    # Feature 4: rating context
    user_rating = None
    can_rate = False
    if swap.status == 'completed':
        try:
            user_rating = SwapRating.objects.get(swap=swap, rated_by=request.user)
        except SwapRating.DoesNotExist:
            pass
        if user_rating is None and (is_owner or is_requester):
            window = swap.created_at + timezone.timedelta(days=7)
            if timezone.now() <= window:
                can_rate = True

    return render(request, 'catalog/swap_detail.html', {
        'swap': swap,
        'is_owner': is_owner,
        'is_requester': is_requester,
        'receipts': receipts,
        'user_has_receipt': user_has_receipt,
        'label_expired': label_expired,
        'dispute': dispute,
        'can_open_dispute': can_open_dispute,
        'user_rating': user_rating,
        'can_rate': can_rate,
    })


@login_required
def upload_receipt(request, swap_pk):
    swap = get_object_or_404(SwapRequest, pk=swap_pk, status='accepted')
    if swap.book_instance.user != request.user:
        messages.error(request, "Only the book owner uploads the shipping receipt.")
        return redirect('swap-detail', pk=swap.pk)

    if swap.receipts.filter(uploaded_by=request.user).exists():
        messages.warning(request, 'You already uploaded a receipt for this swap.')
        return redirect('swap-detail', pk=swap.pk)

    if request.method == 'POST' and request.FILES.get('receipt_image'):
        ShippingReceipt.objects.create(
            swap_request=swap,
            uploaded_by=request.user,
            receipt_image=request.FILES['receipt_image'],
            approved=True,
        )
        swap.status = 'completed'
        swap.book_instance.status = 's'
        swap.book_instance.save()

        # Feature 1: set dispute deadline 48h after completion
        swap.dispute_deadline = timezone.now() + timezone.timedelta(hours=48)
        swap.save()

        Notification.objects.create(
            user=swap.requester,
            swap_request=swap,
            message=f'"{swap.book_instance.book.title}" has been shipped to you!',
        )

        # Feature 5: increment completed_swaps_count for owner
        owner_profile = request.user.profile
        owner_profile.completed_swaps_count += 1
        if owner_profile.completed_swaps_count >= 5 and not owner_profile.is_verified_shipper:
            owner_profile.is_verified_shipper = True
            Notification.objects.create(
                user=request.user,
                message='Congratulations! You have earned the Verified Shipper badge.',
            )
            # Feature 8
            if owner_profile.email_notifications:
                send_notification_email(
                    request.user.email,
                    'BookSwap: You earned the Verified Shipper badge!',
                    'Congratulations! You have completed 5 or more swaps and earned the Verified Shipper badge on BookSwap.',
                )
        owner_profile.save(update_fields=['completed_swaps_count', 'is_verified_shipper'])

        messages.success(request, 'Receipt uploaded! Swap marked as complete.')
        return redirect('swap-detail', pk=swap.pk)

    return render(request, 'catalog/upload_receipt.html', {'swap': swap})


@login_required
def my_swaps(request):
    sent = SwapRequest.objects.filter(requester=request.user).select_related('book_instance__book')
    received = SwapRequest.objects.filter(
        book_instance__user=request.user
    ).select_related('book_instance__book', 'requester')
    transactions = CreditTransaction.objects.filter(user=request.user)[:10]

    # Feature 4: pending ratings – completed swaps within 7 days without a rating from this user
    seven_days_ago = timezone.now() - timezone.timedelta(days=7)
    rated_swap_ids = SwapRating.objects.filter(rated_by=request.user).values_list('swap_id', flat=True)
    pending_ratings = SwapRequest.objects.filter(
        Q(requester=request.user) | Q(book_instance__user=request.user),
        status='completed',
        created_at__gte=seven_days_ago,
    ).exclude(id__in=rated_swap_ids).select_related('book_instance__book')

    return render(request, 'catalog/my_swaps.html', {
        'sent': sent,
        'received': received,
        'transactions': transactions,
        'pending_ratings': pending_ratings,
    })


# ─── Shipping label (Shippo) ─────────────────────────────────────────────────

@login_required
def generate_label(request, swap_pk):
    """Generate a Shippo shipping label for an accepted swap. Owner only."""
    swap = get_object_or_404(SwapRequest, pk=swap_pk, status='accepted')
    if swap.book_instance.user != request.user:
        messages.error(request, "Only the book owner can generate a label.")
        return redirect('swap-detail', pk=swap_pk)

    if swap.label_url:
        messages.info(request, "A label has already been generated for this swap.")
        return redirect('swap-detail', pk=swap_pk)

    try:
        from catalog.utils.encryption import decrypt_address
        from catalog.utils.shippo_client import generate_shipping_label
        from django.conf import settings

        owner = swap.book_instance.user
        requester = swap.requester

        owner_address = decrypt_address(owner.profile.address_encrypted)
        requester_address = decrypt_address(requester.profile.address_encrypted)

        if not owner_address:
            messages.error(request, "Your address is not set. Please update it in Account Settings.")
            return redirect('swap-detail', pk=swap_pk)
        if not requester_address:
            messages.error(request, "The requester hasn't set their address yet.")
            return redirect('swap-detail', pk=swap_pk)

        result = generate_shipping_label(
            from_name=owner.profile.display_name,
            from_street=owner_address,
            from_city=owner.profile.city or '',
            from_zip='00000',
            from_country='VN',
            to_name=requester.profile.display_name,
            to_street=requester_address,
            to_city=requester.profile.city or '',
            to_zip='00000',
            to_country='VN',
        )

        credit_rate = getattr(settings, 'CREDIT_RATE_USD', 3.0)
        credits = max(1, round(result['shipping_cost_usd'] / credit_rate))

        swap.label_url = result['label_url']
        swap.label_expires_at = timezone.now() + timezone.timedelta(hours=24)
        swap.shipping_cost_usd = result['shipping_cost_usd']
        swap.credits_earned = credits
        swap.save(update_fields=['label_url', 'label_expires_at', 'shipping_cost_usd', 'credits_earned'])

        messages.success(request, f'Label generated! Download it within 24 hours. '
                                   f'You will earn {credits} credit(s) when confirmed shipped.')

    except Exception as e:
        messages.error(request, f'Could not generate label: {e}')

    return redirect('swap-detail', pk=swap_pk)


@login_required
def download_label(request, swap_pk):
    """Mark label as downloaded and award credits to the owner."""
    swap = get_object_or_404(SwapRequest, pk=swap_pk)
    if swap.book_instance.user != request.user:
        messages.error(request, "Only the book owner can download this label.")
        return redirect('swap-detail', pk=swap_pk)

    if not swap.label_url:
        messages.error(request, "No label has been generated for this swap.")
        return redirect('swap-detail', pk=swap_pk)

    if swap.label_expires_at and timezone.now() > swap.label_expires_at:
        messages.error(request, "This label has expired. Please generate a new one.")
        return redirect('swap-detail', pk=swap_pk)

    if not swap.label_downloaded:
        swap.label_downloaded = True
        swap.save(update_fields=['label_downloaded'])
        # Award credits to the owner
        profile = request.user.profile
        profile.credit_balance += swap.credits_earned
        profile.save(update_fields=['credit_balance'])
        CreditTransaction.objects.create(
            user=request.user,
            amount=swap.credits_earned,
            description=f'Shipped "{swap.book_instance.book.title}" — label downloaded',
        )
        # Feature 8: notify requester
        if swap.requester.profile.email_notifications:
            send_notification_email(
                swap.requester.email,
                f'BookSwap: Your book has been shipped',
                f'The owner has downloaded the shipping label for "{swap.book_instance.book.title}". '
                f'Your book is on its way!',
            )

    from django.http import HttpResponseRedirect
    return HttpResponseRedirect(swap.label_url)


# ─── Notifications ────────────────────────────────────────────────────────────

@login_required
def notifications(request):
    notifs = request.user.notifications.all()
    # Mark all as read
    notifs.filter(read=False).update(read=True)
    return render(request, 'catalog/notifications.html', {'notifications': notifs})


# ─── Search ──────────────────────────────────────────────────────────────────

def search(request):
    q = request.GET.get("search_query", "").strip()
    from django.db.models import Count
    books = Book.objects.filter(
        Q(title__icontains=q) | Q(author__first_name__icontains=q) | Q(author__last_name__icontains=q)
    ).annotate(available_copies=Count('bookinstance', filter=Q(bookinstance__status='a'))).distinct()

    authors = Author.objects.annotate(
        full_name=Concat('first_name', Value(' '), 'last_name')
    ).filter(full_name__icontains=q)

    return render(request, "catalog/search_results.html", {'books': books, 'authors': authors, 'q': q})


# ─── Feature 1: Dispute System ───────────────────────────────────────────────

@login_required
def open_dispute(request, swap_pk):
    swap = get_object_or_404(SwapRequest, pk=swap_pk)

    if swap.requester != request.user:
        messages.error(request, "Only the requester can open a dispute.")
        return redirect('swap-detail', pk=swap_pk)

    if swap.status != 'completed':
        messages.error(request, "You can only dispute a completed swap.")
        return redirect('swap-detail', pk=swap_pk)

    if not swap.can_open_dispute(request.user):
        messages.error(request, "The dispute window (48 hours) has passed.")
        return redirect('swap-detail', pk=swap_pk)

    if hasattr(swap, 'dispute'):
        messages.warning(request, "A dispute already exists for this swap.")
        return redirect('swap-detail', pk=swap_pk)

    if request.method == 'POST':
        arrived_condition = request.POST.get('arrived_condition', '')
        description = request.POST.get('description', '')
        if not arrived_condition:
            messages.error(request, "Please select the condition the book arrived in.")
            return render(request, 'catalog/open_dispute.html', {'swap': swap})

        dispute = Dispute.objects.create(
            swap=swap,
            opened_by=request.user,
            arrived_condition=arrived_condition,
            description=description,
        )

        owner = swap.book_instance.user
        Notification.objects.create(
            user=owner,
            swap_request=swap,
            message=f'A dispute was opened for swap of "{swap.book_instance.book.title}".',
        )
        Notification.objects.create(
            user=request.user,
            swap_request=swap,
            message=f'Your dispute for "{swap.book_instance.book.title}" has been submitted.',
        )

        # Feature 8
        for party in [owner, request.user]:
            if party.profile.email_notifications:
                send_notification_email(
                    party.email,
                    f'BookSwap: Dispute opened for "{swap.book_instance.book.title}"',
                    f'A dispute has been opened for the swap of "{swap.book_instance.book.title}". '
                    f'Our staff will review and resolve it shortly.',
                )

        messages.success(request, 'Dispute submitted. Our team will review it.')
        return redirect('swap-detail', pk=swap_pk)

    return render(request, 'catalog/open_dispute.html', {'swap': swap})


@staff_member_required
def resolve_dispute(request, dispute_pk):
    dispute = get_object_or_404(Dispute, pk=dispute_pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'requester':
            dispute.status = 'resolved_for_requester'
        elif action == 'owner':
            dispute.status = 'resolved_for_owner'
        else:
            messages.error(request, "Invalid action.")
            return redirect('admin-disputes')

        dispute.resolved_at = timezone.now()
        dispute.resolved_by = request.user
        dispute.save()

        swap = dispute.swap
        owner = swap.book_instance.user
        requester = swap.requester

        Notification.objects.create(
            user=owner,
            swap_request=swap,
            message=f'Dispute for "{swap.book_instance.book.title}" resolved: {dispute.get_status_display()}.',
        )
        Notification.objects.create(
            user=requester,
            swap_request=swap,
            message=f'Dispute for "{swap.book_instance.book.title}" resolved: {dispute.get_status_display()}.',
        )

        # Feature 8
        for party in [owner, requester]:
            if party.profile.email_notifications:
                send_notification_email(
                    party.email,
                    f'BookSwap: Dispute resolved for "{swap.book_instance.book.title}"',
                    f'The dispute for "{swap.book_instance.book.title}" has been resolved: {dispute.get_status_display()}.',
                )

        messages.success(request, f'Dispute resolved: {dispute.get_status_display()}')
    return redirect('admin-disputes')


@staff_member_required
def admin_disputes(request):
    disputes = Dispute.objects.filter(status='open').select_related(
        'swap__book_instance__book', 'opened_by__profile'
    ).order_by('opened_at')
    return render(request, 'catalog/admin_disputes.html', {'disputes': disputes})


# ─── Feature 2: Wishlist ─────────────────────────────────────────────────────

@login_required
def wishlist(request):
    items = Wishlist.objects.filter(user=request.user).order_by('-created_at')
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        author = request.POST.get('author', '').strip()
        isbn = request.POST.get('isbn', '').strip()
        if title:
            Wishlist.objects.create(
                user=request.user, title=title, author=author, isbn=isbn
            )
            messages.success(request, f'"{title}" added to your wishlist.')
            return redirect('wishlist')
        else:
            messages.error(request, 'Please enter a book title.')
    return render(request, 'catalog/wishlist.html', {'items': items})


@login_required
def delete_wishlist(request, pk):
    item = get_object_or_404(Wishlist, pk=pk, user=request.user)
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Wishlist item removed.')
    return redirect('wishlist')


@login_required
def mark_fulfilled(request, pk):
    item = get_object_or_404(Wishlist, pk=pk, user=request.user)
    if request.method == 'POST':
        item.fulfilled = True
        item.save(update_fields=['fulfilled'])
        messages.success(request, f'"{item.title}" marked as fulfilled.')
    return redirect('wishlist')


def request_board(request):
    items = Wishlist.objects.filter(fulfilled=False).select_related('user__profile').order_by('-created_at')
    return render(request, 'catalog/request_board.html', {'items': items})


# ─── Feature 4: Swap Rating ───────────────────────────────────────────────────

@login_required
def rate_swap(request, swap_pk):
    swap = get_object_or_404(SwapRequest, pk=swap_pk, status='completed')
    is_owner = swap.book_instance.user == request.user
    is_requester = swap.requester == request.user

    if not (is_owner or is_requester):
        messages.error(request, "You are not part of this swap.")
        return redirect('my-swaps')

    # check 7-day window
    window = swap.created_at + timezone.timedelta(days=7)
    if timezone.now() > window:
        messages.error(request, "The rating window (7 days) has passed.")
        return redirect('swap-detail', pk=swap_pk)

    # check not already rated
    if SwapRating.objects.filter(swap=swap, rated_by=request.user).exists():
        messages.warning(request, "You have already rated this swap.")
        return redirect('swap-detail', pk=swap_pk)

    # Determine who is being rated
    rated_user = swap.requester if is_owner else swap.book_instance.user

    if request.method == 'POST':
        try:
            score = int(request.POST.get('score', 0))
        except (ValueError, TypeError):
            score = 0
        comment = request.POST.get('comment', '').strip()
        if not (1 <= score <= 5):
            messages.error(request, "Please select a score between 1 and 5.")
            return render(request, 'catalog/rate_swap.html', {'swap': swap, 'rated_user': rated_user})

        SwapRating.objects.create(
            swap=swap,
            rated_by=request.user,
            rated_user=rated_user,
            score=score,
            comment=comment,
        )
        messages.success(request, 'Thank you for your rating!')
        return redirect('swap-detail', pk=swap_pk)

    return render(request, 'catalog/rate_swap.html', {'swap': swap, 'rated_user': rated_user})


# ─── Feature 6: Reading List & Reviews ───────────────────────────────────────

@login_required
def my_shelf(request):
    reading = ReadingList.objects.filter(
        user=request.user, status='reading'
    ).select_related('book')
    completed = ReadingList.objects.filter(
        user=request.user, status='completed'
    ).select_related('book')
    want_to_read = ReadingList.objects.filter(
        user=request.user, status='want_to_read'
    ).select_related('book')
    sections = [
        ('Currently Reading', list(reading)),
        ('Completed', list(completed)),
        ('Want to Read', list(want_to_read)),
    ]
    return render(request, 'catalog/my_shelf.html', {
        'sections': sections,
        'reading': reading,
        'completed': completed,
        'want_to_read': want_to_read,
    })


@login_required
def add_to_shelf(request, book_pk):
    book = get_object_or_404(Book, pk=book_pk)
    if request.method == 'POST':
        status = request.POST.get('status', '')
        valid_statuses = [s for s, _ in ReadingList.STATUS_CHOICES]
        if status not in valid_statuses:
            messages.error(request, "Invalid shelf status.")
            return redirect('book-detail', pk=book_pk)
        obj, created = ReadingList.objects.update_or_create(
            user=request.user, book=book,
            defaults={'status': status},
        )
        if created:
            messages.success(request, f'"{book.title}" added to your shelf as {status.replace("_", " ")}.')
        else:
            messages.success(request, f'"{book.title}" shelf status updated.')
    return redirect('book-detail', pk=book_pk)


@login_required
def remove_from_shelf(request, pk):
    entry = get_object_or_404(ReadingList, pk=pk, user=request.user)
    book_pk = entry.book.pk
    if request.method == 'POST':
        entry.delete()
        messages.success(request, 'Removed from shelf.')
    return redirect('book-detail', pk=book_pk)


@login_required
def write_review(request, book_pk):
    book = get_object_or_404(Book, pk=book_pk)

    # Only if user received this book via a completed swap
    received = SwapRequest.objects.filter(
        requester=request.user,
        book_instance__book=book,
        status='completed',
    ).exists()
    if not received:
        messages.error(request, "You can only review books you received via a completed swap.")
        return redirect('book-detail', pk=book_pk)

    if BookReview.objects.filter(user=request.user, book=book).exists():
        messages.warning(request, "You have already reviewed this book.")
        return redirect('book-detail', pk=book_pk)

    if request.method == 'POST':
        try:
            rating = int(request.POST.get('rating', 0))
        except (ValueError, TypeError):
            rating = 0
        review_text = request.POST.get('review_text', '').strip()
        if not (1 <= rating <= 5):
            messages.error(request, "Please select a rating between 1 and 5.")
            return render(request, 'catalog/write_review.html', {'book': book})
        BookReview.objects.create(
            user=request.user, book=book, rating=rating, review_text=review_text
        )
        messages.success(request, 'Your review has been submitted!')
        return redirect('book-detail', pk=book_pk)

    return render(request, 'catalog/write_review.html', {'book': book})


# ─── Feature 7: Swap History Timeline ────────────────────────────────────────

@login_required
def swap_history(request):
    from django.db.models import Sum
    user = request.user
    swaps = SwapRequest.objects.filter(
        Q(requester=user) | Q(book_instance__user=user),
        status='completed',
    ).select_related('book_instance__book', 'requester', 'book_instance__user').order_by('created_at')

    total_sent = swaps.filter(book_instance__user=user).count()
    total_received = swaps.filter(requester=user).count()
    total_credits = swaps.filter(book_instance__user=user).aggregate(
        total=Sum('credits_earned')
    )['total'] or 0

    # Annotate direction and rating given
    timeline = []
    rated_ids = set(SwapRating.objects.filter(rated_by=user).values_list('swap_id', flat=True))
    for swap in swaps:
        direction = 'Sent' if swap.book_instance.user == user else 'Received'
        rating_given = rated_ids and swap.pk in rated_ids
        timeline.append({
            'swap': swap,
            'direction': direction,
            'rating_given': rating_given,
        })

    stats = {
        'total_sent': total_sent,
        'total_received': total_received,
        'total_credits_earned': total_credits,
        'member_since': user.date_joined,
    }

    return render(request, 'catalog/swap_history.html', {
        'timeline': timeline,
        'stats': stats,
    })
