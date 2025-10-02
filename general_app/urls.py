from django.urls import path
from .views import HomeView, LoginRegisterView, LogoutView, profile_update, math_training, MathTrainingResultsView, about

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('entry/', LoginRegisterView.as_view(), name='entry'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('profile/', profile_update, name='profile'),
    path('math/', math_training, name='mathtraining'),
    path('math/results/', MathTrainingResultsView.as_view(), name='math_training_results'),
    path('about/', about, name='about'),
]
