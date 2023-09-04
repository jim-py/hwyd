from django.contrib.auth.models import User
from django.db import models


class Tasks(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Владелец')
    name = models.CharField(max_length=100, verbose_name='Название')
    description = models.CharField(max_length=255, verbose_name='Описание')
    time = models.TimeField(verbose_name='Время', null=True)
    date = models.DateField(verbose_name='Дата', null=True)
    deadline = models.DateField(verbose_name='Дедлайн', null=True)
    priority = models.CharField(max_length=10, verbose_name='Приоритет')
    done = models.BooleanField(default=False, verbose_name='Сделано')

    class Meta:
        verbose_name = 'Задачу'
        verbose_name_plural = 'Задачи'
