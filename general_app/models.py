from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from pathlib import Path
from uuid import uuid4


def profile_photo_path(instance, filename):
    return f'profiles/{instance.user_id}/{uuid4().hex}{Path(filename).suffix.lower()}'


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    avatar = models.FileField('Фотография профиля', upload_to=profile_photo_path, blank=True)

    @property
    def avatar_is_video(self):
        return bool(self.avatar and Path(self.avatar.name).suffix.lower() == '.webm')

    class Meta:
        verbose_name = 'Профиль пользователя'
        verbose_name_plural = 'Профили пользователей'


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


class GuideOpening(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='guide_openings')
    guide = models.ForeignKey(Guide, on_delete=models.CASCADE, related_name='openings')
    version = models.PositiveIntegerField()
    opened_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Открытие гайда'
        verbose_name_plural = 'Открытия гайдов'
        constraints = [models.UniqueConstraint(fields=['guide', 'version', 'user'], name='unique_guide_version_opening')]

    def __str__(self):
        return f'{self.user} → {self.guide_id}, версия {self.version}'
