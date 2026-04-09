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
    path('author/<int:pk>/update/', views.AuthorUpdate.as_view(), name='author-update'),
    path('author/<int:pk>/delete/', views.AuthorDelete.as_view(), name='author-delete'),

    # create, update and delete books
    path('book/create/', views.BookCreateView.as_view(), name='book-create'),
    path('book/<int:pk>/update/', views.BookUpdateView.as_view(), name='book-update'),
    path('book/<int:pk>/delete/', views.BookDeleteView.as_view(), name='book-delete'),

    # to search for book or author
    path('search/', views.search, name='search-results'),

    # add a copy of an existing book
    path('book/<int:book_pk>/add-copy/', views.add_copy, name='add-copy'),

    # swaps
    path('swap/request/<uuid:pk>/', views.request_swap, name='request-swap'),
    path('swap/<int:pk>/', views.swap_detail, name='swap-detail'),
    path('swap/<int:swap_pk>/receipt/', views.upload_receipt, name='upload-receipt'),
    path('swaps/', views.my_swaps, name='my-swaps'),

    # shipping labels
    path('swap/<int:swap_pk>/label/generate/', views.generate_label, name='generate-label'),
    path('swap/<int:swap_pk>/label/download/', views.download_label, name='download-label'),

    # notifications
    path('notifications/', views.notifications, name='notifications'),

    # Feature 1: Dispute system
    path('swap/<int:swap_pk>/dispute/open/', views.open_dispute, name='open-dispute'),
    path('dispute/<int:dispute_pk>/resolve/', views.resolve_dispute, name='resolve-dispute'),
    path('admin/disputes/', views.admin_disputes, name='admin-disputes'),

    # Feature 2: Wishlist
    path('wishlist/', views.wishlist, name='wishlist'),
    path('wishlist/<int:pk>/delete/', views.delete_wishlist, name='delete-wishlist'),
    path('wishlist/<int:pk>/fulfilled/', views.mark_fulfilled, name='wishlist-fulfilled'),
    path('request-board/', views.request_board, name='request-board'),

    # Feature 4: Rating
    path('swap/<int:swap_pk>/rate/', views.rate_swap, name='rate-swap'),

    # Feature 6: Reading list & reviews
    path('shelf/', views.my_shelf, name='my-shelf'),
    path('book/<int:book_pk>/shelf/', views.add_to_shelf, name='add-to-shelf'),
    path('shelf/<int:pk>/remove/', views.remove_from_shelf, name='remove-from-shelf'),
    path('book/<int:book_pk>/review/', views.write_review, name='write-review'),

    # Feature 7: Swap history
    path('swap-history/', views.swap_history, name='swap-history'),
]
