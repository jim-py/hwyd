from django.db import models
from django.contrib.auth.models import User


class MathTrainingResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)
    time_spent = models.DecimalField(max_digits=5, decimal_places=2)
    problems_solved = models.IntegerField()

    def __str__(self):
        return f'{self.user.username} - {self.problems_solved} - {self.time_spent}'
