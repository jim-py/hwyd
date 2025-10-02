from django.shortcuts import render
from django.contrib.auth.decorators import login_required


@login_required(login_url='entry')
def base(request):
    return render(request, 'pomodoro/base.html')
