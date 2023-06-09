from django.contrib import admin

# Register your models here.
from .models import Author, Genre, Book, BookInstance, Language

# admin.site.register(Book)
# admin.site.register(Author)
admin.site.register(Genre)
# admin.site.register(BookInstance)
admin.site.register(Language)

class BooksInstanceInline(admin.TabularInline):
    model = BookInstance

class BooksInline(admin.TabularInline):
    model = Book

# Define the admin class
class AuthorAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'date_of_birth')

    fields = ['first_name', 'last_name', ('date_of_birth')]
    inlines = [BooksInline]

# Register the admin class with the associated model
admin.site.register(Author, AuthorAdmin)



# Register the Admin classes for Book using the decorator
@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'display_genre')
    inlines = [BooksInstanceInline]
   

# Register the Admin classes for BookInstance using the decorator
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





    