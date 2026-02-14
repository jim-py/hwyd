from django.urls import path
from hwyd.views import (start, by_date, create_last_activities, delete_activity, create_activity, global_colors,
                        get_comments, delete_all, user_logout, check_cell, open_group, open_all, change_setting,
                        add_setting, delete_setting, activity_users, export_data_as_json, edit_settings,
                        select_setting, set_timezone)

urlpatterns = [
    path('', start, name="index"),
    path('signout', user_logout, name="user_logout"),
    path('get_comments/<str:picked_date>', get_comments, name="get_comments"),
    path('<str:picked_date>', by_date, name="by_date"),
    path('global_colors/<str:picked_date>', global_colors, name="global_colors"),
    path('create-last-activities/<str:picked_date>', create_last_activities, name="create_last_activities"),
    path('create_activity/<str:picked_date>/<int:is_group>', create_activity, name="create_activity"),
    
    path('settings/', edit_settings, name='edit_settings'),
    path('settings/<int:pk>/', select_setting, name='select_setting'),
    path('add_setting/', add_setting, name="add_setting"),
    path('delete_setting/<int:setting_id>/', delete_setting, name='delete_setting'),
    path('change_setting/', change_setting, name="change_setting"),
    path('check_cell/<str:picked_date>', check_cell, name="check_cell"),
    path('open_all/<str:picked_date>', open_all, name="open_all"),
    path('delete_all/<str:picked_date>', delete_all, name="delete_all"),
    path('delete-activity/', delete_activity, name="delete_activity"),
    path('open_group/', open_group, name="open_group"),

    path('activityusers/', activity_users, name="activity_users"),
    path('export-json/', export_data_as_json, name='export_json'),
    path("set-timezone/", set_timezone, name="set_timezone"),
]
