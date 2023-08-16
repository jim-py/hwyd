from django.urls import path

from hwyd.views import start, by_date, create_last_activities, delete_activity, create_activity, global_colors, get_comments, delete_all

urlpatterns = [
    path('', start, name="index"),
    path('get_comments/<str:picked_date>', get_comments, name="get_comments"),
    path('<str:picked_date>', by_date, name="by_date"),
    path('delete_all/<str:picked_date>', delete_all, name="delete_all"),
    path('global_colors/<str:picked_date>', global_colors, name="global_colors"),
    path('create-last-activities/<str:picked_date>', create_last_activities, name="create_last_activities"),
    path('create_activity/<str:picked_date>/<int:is_group>', create_activity, name="create_activity"),
    path('delete-activity/<int:pk>/<str:picked_date>', delete_activity, name="delete_activity"),
]
