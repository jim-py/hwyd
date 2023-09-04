from django.urls import path
from todo.views import start

urlpatterns = [
    path('', start, name="test"),
]
