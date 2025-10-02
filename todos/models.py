from django.db import models
from django.conf import settings


class Todo(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='todos'
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    checked = models.BooleanField(default=False)
    task_date = models.DateField()

    def __str__(self):
        return self.title
