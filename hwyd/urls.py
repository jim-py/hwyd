from django.urls import path
from hwyd.views import (start, by_date, create_last_activities, delete_activity, create_activity, global_colors,
                        get_comments, delete_all, signin, user_logout, check_cell, open_group, open_all, change_setting,
                        add_setting, delete_setting)

urlpatterns = [
    path('', start, name="index"),
    path('signin', signin, name="start"),
    path('signout', user_logout, name="user_logout"),
    path('get_comments/<str:picked_date>', get_comments, name="get_comments"),
    path('<str:picked_date>', by_date, name="by_date"),
    path('<str:picked_date>/m', by_date, name="mobile_by_date"),
    path('global_colors/<str:picked_date>', global_colors, name="global_colors"),
    path('create-last-activities/<str:picked_date>', create_last_activities, name="create_last_activities"),
    path('create_activity/<str:picked_date>/<int:is_group>', create_activity, name="create_activity"),

    path('add_setting/', add_setting, name="add_setting"),
    path('delete_setting/', delete_setting, name="delete_setting"),
    path('change_setting/', change_setting, name="change_setting"),
    path('check_cell/<str:picked_date>', check_cell, name="check_cell"),
    path('open_all/<str:picked_date>', open_all, name="open_all"),
    path('delete_all/<str:picked_date>', delete_all, name="delete_all"),
    path('delete-activity/', delete_activity, name="delete_activity"),
    path('open_group/', open_group, name="open_group"),
]
