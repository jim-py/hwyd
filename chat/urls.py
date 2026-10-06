from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('messages/', views.messages, name='messages'),
    path('messages/<int:message_id>/', views.message_detail, name='message'),
    path('messages/<int:message_id>/photo/', views.message_photo, name='photo'),
    path('messages/<int:message_id>/attachments/<int:attachment_id>/', views.message_attachment, name='attachment'),
    path('status/', views.status, name='status'),
    path('read/', views.mark_read, name='read'),
]
