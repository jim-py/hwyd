from django import forms
from .models import Settings, Feedback, ScheduledTheme
from .preferences import FONT_FAMILIES, UI_VISIBILITY_FIELDS, THEME_COLOR_FIELDS, validate_theme_color
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm


class RegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super(RegisterForm, self).__init__(*args, **kwargs)
        del self.fields["password2"]
        self.fields["password1"].help_text = None
        self.fields["username"].help_text = None


class LoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(max_length=150, widget=forms.PasswordInput)


class FeedbackForm(forms.ModelForm):
    message = forms.CharField(max_length=3000, strip=True,
                              error_messages={'required': 'Напишите сообщение.',
                                              'max_length': 'Не больше 3000 символов.'})

    class Meta:
        model = Feedback
        fields = ['category', 'message']


class HabitDescriptionField(forms.CharField):
    def to_python(self, value):
        # HTML forms submit CRLF; count a line break like the textarea does.
        return super().to_python(value).replace('\r\n', '\n').replace('\r', '\n')


class HabitDescriptionForm(forms.Form):
    description = HabitDescriptionField(required=False, max_length=3000, strip=False,
                                  error_messages={'max_length': 'Описание должно содержать не больше 3000 символов.'})


class ThemeColorsForm(forms.ModelForm):
    class Meta:
        model = Settings
        fields = THEME_COLOR_FIELDS
        widgets = {
            field: forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color'})
            for field in THEME_COLOR_FIELDS
        }

    def clean(self):
        data = super().clean()
        for field in THEME_COLOR_FIELDS:
            if field in data:
                try:
                    validate_theme_color(data[field])
                except forms.ValidationError as exc:
                    self.add_error(field, exc)
        return data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            if isinstance(instance, Settings) and instance.pk:
                # The separate preferences form may have updated the same row.
                instance.save(update_fields=THEME_COLOR_FIELDS)
            else:
                instance.save()
            self.save_m2m()
        return instance


class ScheduledThemeColorsForm(ThemeColorsForm):
    class Meta(ThemeColorsForm.Meta):
        model = ScheduledTheme


def theme_colors_form(*args, **kwargs):
    from .theme_schedule import scheduled_colors_enabled
    form_class = ScheduledThemeColorsForm if scheduled_colors_enabled() else ThemeColorsForm
    return form_class(*args, **kwargs)


class ScheduledThemeForm(forms.ModelForm):
    name = forms.CharField(max_length=80, strip=True, error_messages={'required': 'Введите название темы.'})
    activation_time = forms.TimeField(input_formats=['%H:%M'],
                                     error_messages={'required': 'Укажите время включения.', 'invalid': 'Укажите время в формате ЧЧ:ММ.'})

    class Meta:
        model = ScheduledTheme
        fields = ('name', 'activation_time', 'is_enabled')


class SettingsForm(forms.ModelForm):
    class Meta:
        model = Settings
        labels = {'showCompletedButton': 'Показывать кнопку выполненных привычек'}
        fields = [
            "showCalendar",
            "showCreateActivity",
            "showCreateActivityGroup",
            "showDeleteActivity",
            "enableSortTable",
            "enableOpenCloseGroups",
            "showDeleteAllActivities",
            "onSounds",
            "showRowColumnLight",
            "showActivityDayLight",
            "fontFamily",
            "showOpenAllGroups",
            "showTabs",
            "vanishing",
            *UI_VISIBILITY_FIELDS,
        ]
        widgets = {
            "fontFamily": forms.Select(
                choices=[(font, font) for font in FONT_FAMILIES],
                attrs={"class": "form-select", "style": "font-family: inherit;"},
            ),
            "vanishing": forms.Select(
                choices=[
                    ("fade", "Плавное исчезновение"),
                    ("slide", "Скольжение"),
                    ("none", "Без эффекта"),
                ],
                attrs={"class": "form-select"},
            ),
        }
