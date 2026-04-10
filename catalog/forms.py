import datetime

from django import forms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from django.forms import ModelForm

from catalog.models import BookInstance, Book, Author


class BookForm(forms.ModelForm):
    """Book create/edit form with a free-text author input instead of a FK dropdown."""

    author_name = forms.CharField(
        max_length=200,
        label='Author',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. J.K. Rowling',
            'id': 'id_author_name',
            'list': 'author-suggestions',
        }),
    )

    class Meta:
        model = Book
        fields = ['title', 'summary', 'genre']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'list': 'title-suggestions',
            }),
        }

    field_order = ['title', 'author_name', 'summary', 'genre']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate from an existing instance's author
        if self.instance and self.instance.pk and self.instance.author:
            a = self.instance.author
            self.fields['author_name'].initial = f'{a.first_name} {a.last_name}'.strip()

    def get_or_create_author(self):
        """Parse author_name and return a matching Author (or create one)."""
        name = self.cleaned_data['author_name'].strip()
        if ',' in name:
            # "Last, First" format
            last_name, _, first_name = name.partition(',')
            last_name = last_name.strip()
            first_name = first_name.strip()
        else:
            # "First Last" — split on the final space
            parts = name.rsplit(' ', 1)
            if len(parts) == 2:
                first_name, last_name = parts[0].strip(), parts[1].strip()
            else:
                first_name, last_name = '', parts[0].strip()

        existing = Author.objects.filter(
            first_name__iexact=first_name,
            last_name__iexact=last_name,
        ).first()
        if existing:
            return existing
        return Author.objects.create(first_name=first_name, last_name=last_name)


class AddCopyForm(forms.ModelForm):
    class Meta:
        model = BookInstance
        fields = ['condition', 'type', 'imprint']
        widgets = {
            'condition': forms.Select(attrs={'class': 'form-control'}),
            'type':      forms.Select(attrs={'class': 'form-control'}),
            'imprint':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Penguin Classics, 2003 (optional)'}),
        }
        labels = {
            'imprint': 'Edition / Publisher',
        }

class RenewBookForm(forms.Form):
    renewal_date = forms.DateField(help_text="Enter a date between now and 4 weeks (default 3). For practice only, need to update this to sth")
    
    def clean_renewal_date(self):
        data = self.cleaned_data['renewal_date']

        # Check if a date is not in the past.
        if data < datetime.date.today():
            raise ValidationError(_('Invalid date - renewal in past'))

        # Check if a date is in the allowed range (+4 weeks from today).
        if data > datetime.date.today() + datetime.timedelta(weeks=4):
            raise ValidationError(_('Invalid date - renewal more than 4 weeks ahead'))

        # Remember to always return the cleaned data.
        return data

    class Meta:
        model = BookInstance
        fields = ['date_posted']
        labels = {'date_posted': _('Renewal date')}
        help_texts = {'date_posted': _('Enter a date between now and 4 weeks (default 3).')}