import datetime

from django import forms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from django.forms import ModelForm

from catalog.models import BookInstance


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