from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('mark-seen/', views.mark_seen, name='mark-seen'),
]
