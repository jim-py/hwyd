from django.urls import path
from .views import HomeView, LoginRegisterView, LogoutView, profile_update, about, mark_guide_viewed, should_show_guide
from .views import mark_guide_opened

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('entry/', LoginRegisterView.as_view(), name='entry'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('profile/', profile_update, name='profile'),
    path('about/', about, name='about'),
    path("guides/<slug:slug>/should-show/", should_show_guide),
    path("guides/<slug:slug>/viewed/", mark_guide_viewed),
    path('guides/<slug:slug>/opened/', mark_guide_opened, name='guide_opened'),
]
