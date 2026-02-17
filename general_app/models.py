from django.db import models
from django.conf import settings
from django.contrib.auth.models import User


class MathTrainingResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)
    time_spent = models.DecimalField(max_digits=5, decimal_places=2)
    problems_solved = models.IntegerField()

    def __str__(self):
        return f'{self.user.username} - {self.problems_solved} - {self.time_spent}'


class Guide(models.Model):
    """
    Описывает onboarding / обучение в системе.
    Один гайд = один сценарий Driver.js
    """

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=200)
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Гайд обучения"
        verbose_name_plural = "Гайды обучения"

    def __str__(self):
        return f"{self.title} (v{self.version})"
    

class UserGuideProgress(models.Model):
    """
    Какие гайды пользователь уже посмотрел
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="guide_progress"
    )

    guide = models.ForeignKey(
        Guide,
        on_delete=models.CASCADE,
        related_name="user_progress"
    )

    viewed = models.BooleanField(default=False)
    viewed_at = models.DateTimeField(null=True, blank=True)
    version_seen = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Просмотр гайда"
        verbose_name_plural = "Просмотры гайдов"
        unique_together = ("user", "guide")
        
    def __str__(self):
        return f"{self.user} → {self.guide}"
