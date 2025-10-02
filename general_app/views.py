from django.contrib.auth.mixins import LoginRequiredMixin
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

from .forms import UserUpdateForm
from django.contrib.auth.forms import PasswordChangeForm
from django.http import HttpResponseRedirect, HttpResponse
from .models import MathTrainingResult
from django.views.generic.list import ListView
from django.db.models import F, ExpressionWrapper, FloatField
from django.db.models.functions import Round


def about(request):
    return render(request, 'general_app/about.html')


class MathTrainingResultsView(LoginRequiredMixin, ListView):
    model = MathTrainingResult
    template_name = 'general_app/mathtraining_results.html'
    context_object_name = 'results'

    def get_queryset(self):
        average_time = ExpressionWrapper(
            Round(F('time_spent') / F('problems_solved'), 2), output_field=FloatField()
        )

        results = MathTrainingResult.objects.all()
        results = results.annotate(average_time=average_time)
        results = results.order_by('problems_solved', 'average_time')

        return results

    def get_context_data(self, **kwargs):
        context = super(MathTrainingResultsView, self).get_context_data(**kwargs)
        results_sorted = {}

        for result in self.get_queryset():
            problems_solved = result.problems_solved

            if problems_solved not in results_sorted:
                results_sorted[problems_solved] = []

            results_sorted[problems_solved].append(result)

        context['results_sorted'] = dict(sorted(results_sorted.items()))

        return context


@login_required(login_url='entry')
def math_training(request):
    if request.method == 'GET':
        return render(request, 'general_app/mathtraining.html')
    elif request.method == 'POST':
        time_spent = request.POST.get('time')
        problems_solved = request.POST.get('examples_solved')
        result = MathTrainingResult(
            user=request.user,
            time_spent=int(time_spent) / 1000,
            problems_solved=int(problems_solved)
        )
        result.save()
        print(result)
        return HttpResponse()


@login_required(login_url='entry')
def profile_update(request):
    if request.method == 'POST':
        profile_form = True if request.POST.get('email', False) else False
        if profile_form:
            user_form = UserUpdateForm(request.POST, instance=request.user)
            password_form = PasswordChangeForm(request.user)
            if user_form.is_valid():
                user_form.save()
                messages.success(request, 'Ваш профиль был успешно обновлен!')
                return redirect('profile')
        else:
            user_form = UserUpdateForm(instance=request.user)
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Ваш пароль был успешно обновлен!')
                return redirect('profile')
    else:
        user_form = UserUpdateForm(instance=request.user)
        password_form = PasswordChangeForm(request.user)

    return render(request, 'general_app/profile.html', {
        'user_form': user_form,
        'password_form': password_form
    })


class LogoutView(DefaultLogoutView):
    next_page = reverse_lazy('home')


class LoginRegisterView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('home')

        type_form = request.GET.get('type')

        login_form = AuthenticationForm()
        register_form = UserCreationForm()
        return render(request, 'general_app/entry.html', {
            'login_form': login_form,
            'register_form': register_form,
            'type_form': type_form,
            'next': request.GET.get('next', '/home/')
        })

    def post(self, request):
        next_url = request.GET.get('next', '/home/')
        login_form, register_form = None, None
        errors = None
        type_form = 'login'

        if 'login' in request.POST:
            login_form = AuthenticationForm(request, data=request.POST)
            if login_form.is_valid():
                user = authenticate(
                    username=login_form.cleaned_data['username'],
                    password=login_form.cleaned_data['password']
                )
                if user is not None:
                    login(request, user)
                    return HttpResponseRedirect(next_url)
                else:
                    errors = ['Неверный логин или пароль']
            else:
                errors = login_form.errors

            register_form = UserCreationForm()

        elif 'register' in request.POST:
            register_form = UserCreationForm(request.POST)
            type_form = 'register'
            if register_form.is_valid():
                user = register_form.save()
                login(request, user)
                return HttpResponseRedirect(next_url)
            else:
                errors = register_form.errors

            login_form = AuthenticationForm()

        return render(request, 'general_app/entry.html', {
            'login_form': login_form,
            'register_form': register_form,
            'errors': errors,
            'type_form': type_form
        })


class HomeView(TemplateView):
    template_name = 'general_app/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context
