from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),

    path('books/', views.BookListView.as_view(), name='books'),
    path('book/<int:pk>', views.BookDetailView.as_view(), name='book-detail'),

    path('authors/', views.AuthorListView.as_view(), name='authors'),
    path('authors/<int:pk>', views.AuthorDetailView.as_view(), name='author-detail'),

    path('genres/', views.GenreListView.as_view(), name='genres'),
    path('genre/<int:pk>', views.GenreDetailView.as_view(), name='genre-detail'),

    path('mybooks/', views.BooksByUserListView.as_view(), name='my-swapped-book'),
    path('allbooks/', views.BooksByAllListView.as_view(), name='all-books'), 

    # Add URLConf for librarian to renew a book.
    path('book/<uuid:pk>/renew/', views.renew_book_librarian, name='renew-book-librarian'),


    # create, update and delete authors
    # path('author/create/', views.AuthorCreate.as_view(), name='author-create'),
    path('author/<int:pk>/update/', views.AuthorUpdate.as_view(), name='author-update'),
    path('author/<int:pk>/delete/', views.AuthorDelete.as_view(), name='author-delete'),


     # create, update and delete books
    path('book/create/', views.BookCreateView.as_view(), name='book-create'),
    path('book/<int:pk>/update/', views.BookUpdateView.as_view(), name='book-update'),
    path('book/<int:pk>/delete/', views.BookDeleteView.as_view(), name='book-delete'),

    # to search for book or author
    path('search/', views.search, name='search-results'),

    
]



