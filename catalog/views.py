from django.shortcuts import render, redirect

from .models import Book, Author, BookInstance, Genre, SwapRequest, ShippingReceipt, PointTransaction
from django.views import generic
from itertools import chain
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Q
import datetime

from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponseRedirect
from django.urls import reverse

from catalog.forms import RenewBookForm, AddCopyForm

from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from catalog.models import Author
from catalog.models import Book

from django.db.models import Value
from django.db.models.functions import Concat

from django.utils.text import slugify
from django.contrib import messages
from extra_views import CreateWithInlinesView, InlineFormSetFactory


def index(request):
    """View function for home page of site."""

    # Generate counts of some of the main objects
    num_books = Book.objects.all().count()
    num_instances = BookInstance.objects.all().count()
    num_genre = Genre.objects.all().count()

    # Available books (status = 'a')
    num_instances_available = BookInstance.objects.filter(status__exact='a').count()

    # The 'all()' is implied by default.
    num_authors = Author.objects.count()

    # Number of visits to this view, as counted in the session variable.
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

    # Render the HTML template index.html with the data in the context variable
    return render(request, 'index.html', context=context)

class BookListView(generic.ListView):
    """Generic class-based view for a list of books."""
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
    """Generic class-based detail view for a book."""
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
    """Generic class-based list view for a list of authors."""
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
    """Generic class-based detail view for an author."""
    model = Author

class GenreListView(generic.ListView):
    """Generic class-based list view for a list of genres."""
    model = Genre
    paginate_by = 10 # reducing the number of items displayed on each page

class GenreDetailView(generic.DetailView):
    """Generic class-based detail view for an genre."""
    model = Genre




class BooksByUserListView(LoginRequiredMixin, generic.ListView):
    """List all copies the logged-in user has listed for swap."""
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
    """Generic class-based view listing books on swapped, only visible to staff --user who can mark as swapped."""
    model = BookInstance
    template_name = 'catalog/bookinstance_list_by_user.html'
    paginate_by = 10

    def get_queryset(self):
        return (
            BookInstance.objects.order_by('date_posted')
        )
    
@login_required
@permission_required('catalog.can_mark_swapped', raise_exception=True)
def renew_book_librarian(request, pk):
    """View function for renewing a specific BookInstance by librarian."""

    """
    Get_object_or_404:
    - Returns a specified object from a model based on its primary key value, and raises an Http404 exception (not found) if the record does not exist.
    - Use the pk argument in get_object_or_404() to get the current BookInstance 
        (if this does not exist, the view will immediately exit and the page will display a "not found" error)
    """
    book_instance = get_object_or_404(BookInstance, pk=pk)

    # If this is a POST request then process the Form data
    if request.method == 'POST':

        # Create a form instance and populate it with data from the request (binding):
        form = RenewBookForm(request.POST)

        # Check if the form is valid:
        if form.is_valid():
            # process the data in form.cleaned_data as required (here we just write it to the model due_back field)
            book_instance.due_back = form.cleaned_data['renewal_date']
            book_instance.save()

            """
            Redirect to a new URL:
            -  HttpResponseRedirect: This creates a redirect to a specified URL (HTTP status code 302).
            -  reverse(): This generates a URL from a URL configuration name and a set of arguments. 
                It is the Python equivalent of the url tag that we've been using in our templates.
            """
            return HttpResponseRedirect(reverse('all-books'))

    # If this is a GET (or any other method) create the default form.
    else:
        proposed_renewal_date = datetime.date.today() + datetime.timedelta(weeks=3)
        form = RenewBookForm(initial={'renewal_date': proposed_renewal_date})

    context = {
        'form': form,
        'book_instance': book_instance,
    }

    # render() to create the HTML page, specifying the template and a context that contains our form
    return render(request, 'catalog/book_renew_librarian.html', context)


#  Create, update and delete authors
class AuthorCreate(InlineFormSetFactory):
    model = Author
    fields = ['first_name', 'last_name', 'date_of_birth']

class AuthorUpdate(UpdateView):
    model = Author
    fields = '__all__' # Not recommended (potential security issue if more fields added)

class AuthorDelete(DeleteView):
    model = Author
    success_url = reverse_lazy('authors')



#  Create, update and delete books
class BookCreateView(LoginRequiredMixin, CreateWithInlinesView):
    model = Book
    inclines = [Author]
    fields = ['title', 'author', 'summary', 'genre']
    template_name = 'catalog/book_form.html'

    def get_success_url(self):
        messages.success(
            self.request, 'Your book-swap has been created successfully.')
        return self.object.get_absolute_url()

class BookUpdateView(LoginRequiredMixin, UpdateView):
    model = Book
    fields = ['title', 'author', 'summary',  'genre']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        update = True
        context['update'] = update

        return context

    def get_success_url(self):
        messages.success(
            self.request, 'Your book has been updated successfully.')
        return reverse_lazy('book')

    def get_queryset(self):
        return self.model.objects.filter(author=self.request.user)

class BookDeleteView(LoginRequiredMixin, DeleteView):
    model = Book
    def get_success_url(self):
        messages.success(
            self.request, 'Your post has been deleted successfully.')
        return reverse_lazy('book')

    def get_queryset(self):
        return self.model.objects.filter(author=self.request.user)

import math

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


@login_required
def add_copy(request, book_pk):
    """Let a user add themselves as an owner of an existing book."""
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


@login_required
def request_swap(request, pk):
    """Request to swap a specific BookInstance."""
    book_instance = get_object_or_404(BookInstance, pk=pk, status='a')

    if book_instance.user == request.user:
        messages.error(request, "You can't swap your own book.")
        return redirect('book-detail', pk=book_instance.book.pk)

    profile = request.user.profile
    if profile.points < 10:
        messages.error(request, "You need at least 10 points to request a swap.")
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
            points_spent=10,
        )
        profile.points -= 10
        profile.save(update_fields=['points'])
        PointTransaction.objects.create(
            user=request.user,
            amount=-10,
            description=f'Swap request for "{book_instance.book.title}"',
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
            messages.success(request, 'Swap accepted! Both parties should ship their books.')
        elif action == 'reject' and swap.status == 'pending':
            swap.status = 'rejected'
            swap.save()
            # Refund points
            swap.requester.profile.points += swap.points_spent
            swap.requester.profile.save(update_fields=['points'])
            PointTransaction.objects.create(
                user=swap.requester,
                amount=swap.points_spent,
                description=f'Refund — swap rejected for "{swap.book_instance.book.title}"',
            )
            messages.info(request, 'Swap rejected. Points refunded to requester.')

    receipts = swap.receipts.all()
    user_has_receipt = receipts.filter(uploaded_by=request.user).exists()
    return render(request, 'catalog/swap_detail.html', {
        'swap': swap,
        'is_owner': is_owner,
        'is_requester': is_requester,
        'receipts': receipts,
        'user_has_receipt': user_has_receipt,
    })


@login_required
def upload_receipt(request, swap_pk):
    """Only the book owner uploads the shipping receipt to earn points."""
    swap = get_object_or_404(SwapRequest, pk=swap_pk, status='accepted')
    if swap.book_instance.user != request.user:
        messages.error(request, "Only the book owner uploads the shipping receipt.")
        return redirect('swap-detail', pk=swap.pk)

    if swap.receipts.filter(uploaded_by=request.user).exists():
        messages.warning(request, 'You already uploaded a receipt for this swap.')
        return redirect('swap-detail', pk=swap.pk)

    if request.method == 'POST' and request.FILES.get('receipt_image'):
        receipt = ShippingReceipt.objects.create(
            swap_request=swap,
            uploaded_by=request.user,
            receipt_image=request.FILES['receipt_image'],
            approved=True,
        )
        # Owner earns points for shipping
        request.user.profile.points += receipt.points_awarded
        request.user.profile.save(update_fields=['points'])
        PointTransaction.objects.create(
            user=request.user,
            amount=receipt.points_awarded,
            description=f'Shipped "{swap.book_instance.book.title}" to {swap.requester.username}',
        )
        # Mark swap + copy as completed
        swap.status = 'completed'
        swap.book_instance.status = 's'
        swap.book_instance.save()
        swap.save()
        messages.success(request, f'Receipt uploaded! You earned {receipt.points_awarded} points.')
        return redirect('swap-detail', pk=swap.pk)

    return render(request, 'catalog/upload_receipt.html', {'swap': swap})


@login_required
def my_swaps(request):
    sent = SwapRequest.objects.filter(requester=request.user).select_related('book_instance__book')
    received = SwapRequest.objects.filter(book_instance__user=request.user).select_related('book_instance__book', 'requester')
    transactions = PointTransaction.objects.filter(user=request.user)[:10]
    return render(request, 'catalog/my_swaps.html', {
        'sent': sent,
        'received': received,
        'transactions': transactions,
    })


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

