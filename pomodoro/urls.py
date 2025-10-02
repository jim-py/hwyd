from django.urls import path
from .views import base

app_name = 'pomodoro'
urlpatterns = [
    path('', base, name='base'),
]
