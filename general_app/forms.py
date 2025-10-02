from django.utils.translation import gettext_lazy as _
from django.contrib.auth.forms import PasswordChangeForm
from django import forms
from django.contrib.auth.models import User


class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField(label=_('Электронная почта'))

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        labels = {
            'username': _('Логин'),
            'first_name': _('Имя'),
            'last_name': _('Фамилия'),
        }
        help_texts = {
            'username': None,
            'email': None,
        }


class CustomPasswordChangeForm(PasswordChangeForm):

    def __init__(self, *args, **kwargs):
        super(CustomPasswordChangeForm, self).__init__(*args, **kwargs)
        for fieldname in ['old_password', 'new_password1', 'new_password2']:
            self.fields[fieldname].help_text = None
            self.fields[fieldname].label = _(self.fields[fieldname].label)
