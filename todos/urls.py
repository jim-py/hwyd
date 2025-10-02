from django.urls import path
from . import views

app_name = 'todos'
urlpatterns = [
    path('', views.redirect_to_today, name='index'),
    path('<int:year>-<int:month>-<int:day>/', views.IndexView.as_view(), name='index_by_date'),
    path('<int:todo_id>/update/', views.update, name='update'),
    path('add/', views.add, name='add'),
    path('load-todos/', views.load_todos_from_json, name='load_todos'),
    path('<int:todo_id>/delete/', views.delete, name='delete'),
]
