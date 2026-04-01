from django.shortcuts import render, redirect
from django.views import generic
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q, Value
from django.db.models.functions import Concat
import datetime
import math

from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.utils import timezone
from django.contrib import messages
from extra_views import CreateWithInlinesView, InlineFormSetFactory

from .models import Book, Author, BookInstance, Genre, SwapRequest, ShippingReceipt, CreditTransaction, Notification
from catalog.forms import RenewBookForm, AddCopyForm


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
        ).order_by('popularity_rank', 'title')
        if self.request.GET.get('available'):
            qs = qs.filter(available_copies__gt=0)
        return qs


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

        Notification.objects.create(
            user=book_instance.user,
            swap_request=swap,
            message=(
                f'{request.user.profile.display_name} requested your copy of '
                f'"{book_instance.book.title}".'
            ),
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
            messages.info(request, 'Swap rejected. 1 credit refunded to requester.')

    receipts = swap.receipts.all()
    user_has_receipt = receipts.filter(uploaded_by=request.user).exists()
    label_expired = False
    if swap.label_expires_at:
        label_expired = timezone.now() > swap.label_expires_at

    return render(request, 'catalog/swap_detail.html', {
        'swap': swap,
        'is_owner': is_owner,
        'is_requester': is_requester,
        'receipts': receipts,
        'user_has_receipt': user_has_receipt,
        'label_expired': label_expired,
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
        swap.save()
        Notification.objects.create(
            user=swap.requester,
            swap_request=swap,
            message=f'"{swap.book_instance.book.title}" has been shipped to you!',
        )
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
    return render(request, 'catalog/my_swaps.html', {
        'sent': sent,
        'received': received,
        'transactions': transactions,
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
