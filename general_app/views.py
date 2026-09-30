from django.views.generic import TemplateView
from django.views import View
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.views import LogoutView as DefaultLogoutView
from django.urls import reverse_lazy
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse

from .forms import UserUpdateForm
from django.contrib.auth.forms import PasswordChangeForm
from django.http import HttpResponseRedirect
from .models import Guide, UserGuideProgress
from django.views.decorators.http import require_POST


def about(request):
    return render(request, "general_app/about.html")


@login_required(login_url="entry")
def profile_update(request):
    if request.method == "POST":
        profile_form = True if request.POST.get("email", False) else False
        if profile_form:
            user_form = UserUpdateForm(request.POST, instance=request.user)
            password_form = PasswordChangeForm(request.user)
            if user_form.is_valid():
                user_form.save()
                messages.success(request, "Ваш профиль был успешно обновлен!")
                return redirect("profile")
        else:
            user_form = UserUpdateForm(instance=request.user)
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Ваш пароль был успешно обновлен!")
                return redirect("profile")
    else:
        user_form = UserUpdateForm(instance=request.user)
        password_form = PasswordChangeForm(request.user)

    return render(
        request,
        "general_app/profile.html",
        {"user_form": user_form, "password_form": password_form},
    )


class LogoutView(DefaultLogoutView):
    next_page = reverse_lazy("home")


class LoginRegisterView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("home")

        type_form = request.GET.get("type")

        login_form = AuthenticationForm()
        register_form = UserCreationForm()
        return render(
            request,
            "general_app/entry.html",
            {
                "login_form": login_form,
                "register_form": register_form,
                "type_form": type_form,
                "next": request.GET.get("next", "/home/"),
            },
        )

    def post(self, request):
        next_url = request.GET.get("next", "/home/")
        login_form, register_form = None, None
        errors = None
        type_form = "login"

        if "login" in request.POST:
            login_form = AuthenticationForm(request, data=request.POST)
            if login_form.is_valid():
                user = authenticate(
                    username=login_form.cleaned_data["username"],
                    password=login_form.cleaned_data["password"],
                )
                if user is not None:
                    login(request, user)
                    return HttpResponseRedirect(next_url)
                else:
                    errors = ["Неверный логин или пароль"]
            else:
                errors = login_form.errors

            register_form = UserCreationForm()

        elif "register" in request.POST:
            register_form = UserCreationForm(request.POST)
            type_form = "register"
            if register_form.is_valid():
                user = register_form.save(commit=False)
                user.first_name = request.POST.get('first_name', '')
                user.last_name = request.POST.get('last_name', '')
                user.email = request.POST.get('email', '')
                user.save()

                login(request, user)
                return HttpResponseRedirect(next_url)
            else:
                errors = register_form.errors

            login_form = AuthenticationForm()

        return render(
            request,
            "general_app/entry.html",
            {
                "login_form": login_form,
                "register_form": register_form,
                "errors": errors,
                "type_form": type_form,
            },
        )


class HomeView(TemplateView):
    template_name = "general_app/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


def should_show_guide(request, slug):
    guide = Guide.objects.get(slug=slug, is_active=True)

    progress, _ = UserGuideProgress.objects.get_or_create(
        user=request.user,
        guide=guide
    )

    should_show = (
        not progress.viewed
        or progress.version_seen < guide.version
    )

    return JsonResponse({
        "show": should_show,
        "version": guide.version
    })


@require_POST
def mark_guide_viewed(request, slug):
    guide = Guide.objects.get(slug=slug)

    progress, _ = UserGuideProgress.objects.get_or_create(
        user=request.user,
        guide=guide
    )

    progress.viewed = True
    progress.version_seen = guide.version
    progress.viewed_at = timezone.now()
    progress.save()

    return JsonResponse({"status": "ok"})
