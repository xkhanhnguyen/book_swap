from django.contrib import admin
from django.utils import timezone

from .models import (
    Author, Genre, Book, BookInstance, Language,
    Dispute, Wishlist, SwapRating, ReadingList, BookReview, SwapRequest,
)

admin.site.register(Genre)
admin.site.register(Language)
admin.site.register(Wishlist)
admin.site.register(SwapRating)
admin.site.register(ReadingList)
admin.site.register(BookReview)


class BooksInstanceInline(admin.TabularInline):
    model = BookInstance


class BooksInline(admin.TabularInline):
    model = Book


class AuthorAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'date_of_birth')
    fields = ['first_name', 'last_name', ('date_of_birth')]
    inlines = [BooksInline]


admin.site.register(Author, AuthorAdmin)


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'display_genre')
    inlines = [BooksInstanceInline]


@admin.register(BookInstance)
class BookInstanceAdmin(admin.ModelAdmin):
    list_display = ('book', 'condition', 'type', 'status', 'user', 'date_posted', 'id')
    list_filter = ('status', 'date_posted')

    fieldsets = (
        (None, {
            'fields': ('book', 'condition', 'type', 'imprint', 'id')
        }),
        ('Availability', {
            'fields': ('status', 'user', 'date_posted')
        }),
    )


def resolve_for_requester(modeladmin, request, queryset):
    queryset.update(status='resolved_for_requester', resolved_at=timezone.now(), resolved_by=request.user)
resolve_for_requester.short_description = 'Resolve selected disputes in favour of Requester'


def resolve_for_owner(modeladmin, request, queryset):
    queryset.update(status='resolved_for_owner', resolved_at=timezone.now(), resolved_by=request.user)
resolve_for_owner.short_description = 'Resolve selected disputes in favour of Owner'


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = ('pk', 'swap', 'opened_by', 'arrived_condition', 'status', 'opened_at', 'resolved_at')
    list_filter = ('status',)
    actions = [resolve_for_requester, resolve_for_owner]
    readonly_fields = ('opened_at',)
