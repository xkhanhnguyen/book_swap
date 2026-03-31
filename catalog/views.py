from django.shortcuts import render, redirect

from .models import Book, Author, BookInstance, Genre
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

from catalog.forms import RenewBookForm

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
        return Book.objects.order_by('popularity_rank', 'title')
    

class BookDetailView(generic.DetailView):
    """Generic class-based detail view for a book."""
    model = Book

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['swap_offers'] = (
            BookInstance.objects
            .filter(book=self.object, status='a')
            .select_related('user')
            .order_by('date_posted')
        )
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
    """Generic class-based view listing books on swapped to current user."""
    model = BookInstance
    template_name = 'catalog/bookinstance_list_by_user.html'
    paginate_by = 10

    def get_queryset(self):
        # logged_in_user_posts = BookInstance.objects.filter(author=self.request.user)
        # return render(self.request, 'blog/post_list.html', {'posts': logged_in_user_posts})
        return (
            BookInstance.objects.filter(user=self.request.user)
            .filter(status__exact='s')
            .order_by('date_posted')
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

def search(request):
    q = request.GET["search_query"] #The empty string handles an empty "request"

    books = Book.objects.filter(title__icontains=q)
    authors = Author.objects.annotate(full_name=Concat('first_name', Value(' '), 'last_name')).filter(full_name__icontains=q) 
    return render(request, "catalog/search_results.html", {'books':books, 'authors':authors, 'page_name':'Search Results', 'q':q})

