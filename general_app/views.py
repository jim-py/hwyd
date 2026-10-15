from django.views.generic import TemplateView
from django.views import View
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.views import LogoutView as DefaultLogoutView
from django.urls import reverse, reverse_lazy
from django.conf import settings
from calendar import monthrange
from datetime import date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse

from .forms import UserUpdateForm, ProfilePhotoForm
from django.contrib.auth.forms import PasswordChangeForm
from django.http import HttpResponseRedirect
from .models import Guide, UserGuideProgress, UserProfile, GuideOpening
from .guides import GUIDE_MODULES
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_safe
from django.http import HttpResponse
from .seo import canonical_url, public_origin, PUBLIC_PAGE_NAMES
from django.db import transaction
import logging


def about(request):
    today = timezone.localdate()

    def experience(start):
        months = max(0, (today.year - start.year) * 12 + today.month - start.month)
        years, months = divmod(months, 12)

        def amount(value, forms):
            index = 2 if 11 <= value % 100 <= 14 else 0 if value % 10 == 1 else 1 if 2 <= value % 10 <= 4 else 2
            return f'{value} {forms[index]}'

        return ' '.join(text for text in (
            amount(years, ('год', 'года', 'лет')) if years else '',
            amount(months, ('месяц', 'месяца', 'месяцев')) if months else '',
        ) if text) or 'меньше месяца'

    return render(request, "general_app/about.html", {
        'canonical_url': canonical_url('about'),
        'experience_1c': experience(date(2023, 9, 13)),
        'experience_django': experience(date(2022, 10, 1)),
        'experience_self': experience(date(2022, 1, 1)),
    })


class PublicGuideView(TemplateView):
    page_name = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['canonical_url'] = canonical_url(self.page_name)
        return context


@require_safe
def robots(request):
    return HttpResponse('User-agent: *\nAllow: /\n\nSitemap: ' + canonical_url('sitemap') + '\n',
                        content_type='text/plain; charset=utf-8')


@require_safe
def sitemap(request):
    if not public_origin().startswith('https://'):
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured('The public sitemap requires an HTTPS PUBLIC_SITE_ORIGIN.')
    return render(request, 'general_app/sitemap.xml',
                  {'locations': [canonical_url(name) for name in PUBLIC_PAGE_NAMES]},
                  content_type='application/xml; charset=utf-8')


@login_required(login_url="entry")
def profile_update(request):
    profile = UserProfile.objects.filter(user=request.user).first()
    photo_instance = profile or UserProfile(user=request.user)
    photo_form = ProfilePhotoForm(instance=photo_instance)
    if request.method == "POST":
        profile_form = True if request.POST.get("email", False) else False
        if request.POST.get('profile_action') == 'avatar':
            old_name = photo_instance.avatar.name
            storage = photo_instance.avatar.storage
            photo_form = ProfilePhotoForm(request.POST, request.FILES, instance=photo_instance)
            user_form = UserUpdateForm(instance=request.user)
            password_form = PasswordChangeForm(request.user)
            if photo_form.is_valid():
                photo_form.save()
                if old_name and old_name != photo_instance.avatar.name:
                    def delete_previous_photo():
                        try:
                            storage.delete(old_name)
                        except OSError:
                            logging.getLogger(__name__).warning('Could not remove replaced profile photo', exc_info=True)
                    transaction.on_commit(delete_previous_photo)
                messages.success(request, 'Фотография профиля обновлена!')
                return redirect('profile')
        elif profile_form:
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
        {"user_form": user_form, "password_form": password_form, "photo_form": photo_form, "profile": profile},
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
                "next": request.GET.get("next", reverse('home')),
            },
        )

    def post(self, request):
        next_url = request.GET.get("next", reverse('home'))
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
                "next": next_url,
            },
        )


class HomeView(TemplateView):
    template_name = "general_app/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['canonical_url'] = canonical_url('home')
        today = timezone.localdate()
        month = today.replace(day=1)
        total_days = monthrange(today.year, today.month)[1]
        mobile_start = max(1, min(today.day - 3, total_days - 4))
        days = [
            {'number': day, 'weekend': month.replace(day=day).weekday() >= 5, 'today': day == today.day,
             'mobile_visible': mobile_start <= day < mobile_start + 5}
            for day in range(1, total_days + 1)
        ]
        context['preview_month'] = month
        context['preview_days'] = days
        context['preview_habits'] = [
            {'name': name, 'cells': [dict(day, done=day['number'] < today.day and (day['number'] + row) % 3 != 0)
                                     for day in days]}
            for row, name in enumerate(('Читать', 'Гулять', 'Зарядка'))
        ]
        context['preview_group'] = {
            'name': 'Здоровье',
            'cells': [dict(day, percent=round(sum(habit['cells'][index]['done']
                                                 for habit in context['preview_habits']) / len(context['preview_habits']) * 100))
                      for index, day in enumerate(days)],
        }
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


@login_required(login_url='entry')
@require_POST
def mark_guide_opened(request, slug):
    if slug not in GUIDE_MODULES:
        return JsonResponse({'error': 'Гайд не поддерживается.'}, status=404)
    guide = get_object_or_404(Guide, slug=slug, is_active=True)
    GuideOpening.objects.get_or_create(user=request.user, guide=guide, version=guide.version)
    return JsonResponse({'status': 'ok', 'version': guide.version})
