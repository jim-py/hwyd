from django import forms
from .models import Settings
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


class SettingsForm(forms.ModelForm):
    class Meta:
        model = Settings
        fields = [
            "backgroundColor",
            "tableHeadColorWeekend",
            "tableHeadColor",
            "tableHeadTextColor",
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
            "rowColumnLight",
            "fontFamily",
            "showOpenAllGroups",
            "showTabs",
            "vanishing",
        ]
        widgets = {
            "backgroundColor": forms.TextInput(
                attrs={"type": "color", "class": "form-control form-control-color"}
            ),
            "tableHeadColorWeekend": forms.TextInput(
                attrs={"type": "color", "class": "form-control form-control-color"}
            ),
            "tableHeadColor": forms.TextInput(
                attrs={"type": "color", "class": "form-control form-control-color"}
            ),
            "tableHeadTextColor": forms.TextInput(
                attrs={"type": "color", "class": "form-control form-control-color"}
            ),
            "rowColumnLight": forms.TextInput(
                attrs={"type": "color", "class": "form-control form-control-color"}
            ),
            "fontFamily": forms.Select(
                choices=[
                    ("Consolas", "Consolas"),
                    ("Montserrat", "Montserrat"),
                    ("Montserrat Alternates", "Montserrat Alternates"),
                    ("Georgia", "Georgia"),
                    ("JetBrains Mono", "JetBrains Mono"),
                    ("Arial", "Arial"),
                    ("Courier New", "Courier New"),
                    ("Lucida Console", "Lucida Console"),
                    ("Trebuchet MS", "Trebuchet MS"),
                    ("Istok Web", "Istok Web"),
                    ("Roboto Mono", "Roboto Mono"),
                    ("Inter", "Inter"),
                    ("Ubuntu", "Ubuntu"),
                    ("Comic Sans MS", "Comic Sans MS"),
                ],
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
