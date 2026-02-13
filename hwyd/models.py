from django.contrib.auth.models import User
from django.db import models
from django.forms.models import model_to_dict
from datetime import timedelta
from backports.zoneinfo import ZoneInfo

from django.db import models
from django.contrib.auth.models import User


class UserActivityLog(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='activity_logs'
    )

    # Дата в локальной timezone пользователя
    date = models.DateField(verbose_name='Дата посещения')

    # Храним UTC
    first_visit = models.DateTimeField(verbose_name='Первое посещение (UTC)')
    last_visit = models.DateTimeField(verbose_name='Последнее посещение (UTC)')

    # TZ пользователя на момент визита
    timezone = models.CharField(
        max_length=64,
        default="Europe/Moscow",
        verbose_name="Часовой пояс"
    )

    class Meta:
        verbose_name = 'Лог активности пользователя'
        verbose_name_plural = 'Логи активности пользователей'
        unique_together = ('user', 'date')

    def __str__(self):
        return f"{self.user.username} — {self.date}"
    
    def get_login_streak(self):
        """
        Возвращает текущий стрик пользователя на основе date.
        """

        dates = (
            UserActivityLog.objects
            .filter(user=self.user)
            .order_by('-date')
            .values_list('date', flat=True)
        )

        if not dates:
            return 0

        streak = 1
        previous_date = dates[0]

        for current_date in dates[1:]:
            if previous_date - current_date == timedelta(days=1):
                streak += 1
                previous_date = current_date
            else:
                break

        return streak

    @property
    def first_visit_local(self):
        dt = self.first_visit.astimezone(ZoneInfo(self.timezone))
        return dt.replace(tzinfo=None)

    @property
    def last_visit_local(self):
        dt = self.last_visit.astimezone(ZoneInfo(self.timezone))
        return dt.replace(tzinfo=None)


class CustomFieldsUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    lastActive = models.DateTimeField(verbose_name='Последнее посещение')
    answers = models.TextField('Ответы')

    class Meta:
        verbose_name = 'Кастомные поля'
        verbose_name_plural = 'Кастомные поля'

    def __str__(self):
        return f'Пользователь {self.user}, последний заход в {self.lastActive.strftime("%d.%m.%Y %H:%M:%S")} ответил {self.answers != ""}'


class ActivitiesConnection(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Владелец')
    group = models.ForeignKey('Activities', on_delete=models.CASCADE, verbose_name='Группа', related_name='group')
    activity = models.ForeignKey('Activities', on_delete=models.CASCADE, verbose_name='Активность', related_name='activity')

    class Meta:
        verbose_name = 'Связь активностей'
        verbose_name_plural = 'Связи активностей'

    def __str__(self):
        return f'Группа: {self.group.name} | Активность: {self.activity.name} | Пользователь: {self.user}'


class Activities(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Владелец')
    name = models.CharField(max_length=100, verbose_name='Название')
    date = models.CharField(max_length=7, verbose_name='Месяц')
    backgroundColor = models.CharField(max_length=7, verbose_name='Цвет')
    color = models.CharField(max_length=7, verbose_name='Цвет текста')
    marks = models.TextField(verbose_name='Отметки')
    number = models.IntegerField(verbose_name='Сортировка')
    isGroup = models.BooleanField(verbose_name='Это группа')
    beginDay = models.IntegerField(verbose_name='Начало')
    endDay = models.IntegerField(verbose_name='Конец')
    isOpen = models.BooleanField(verbose_name='Раскрыта')
    cellsComments = models.TextField(verbose_name='Надписи клеток')
    onOffCells = models.TextField(verbose_name='Выключение клеток')
    hide = models.BooleanField(verbose_name='Спрятать')

    class Meta:
        verbose_name = 'Активность'
        verbose_name_plural = 'Активности'
        ordering = ['number']

    def __str__(self):
        return f'Активность: {self.name} | Пользователь: {self.user} | Месяц: {self.date}'

    def get_changed_fields(self, old_instance):
        old_instance_dict = model_to_dict(old_instance)
        new_instance_dict = model_to_dict(self)
        changed_fields = {}

        for field, old_value in old_instance_dict.items():
            new_value = new_instance_dict[field]
            if old_value != new_value:
                changed_fields[field] = new_value

        return changed_fields


class Settings(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название')
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Владелец')
    backgroundColor = models.CharField(max_length=7, verbose_name='Фон')
    tableHeadColorWeekend = models.CharField(max_length=7, verbose_name='Выходные')
    tableHeadColor = models.CharField(max_length=7, verbose_name='Фон заголовка таблицы')
    tableHeadTextColor = models.CharField(max_length=7, verbose_name='Текст заголовка таблицы')
    showCalendar = models.BooleanField(verbose_name='Календарь')
    showCreateActivity = models.BooleanField(verbose_name='Создание привычки')
    showCreateActivityGroup = models.BooleanField(verbose_name='Создание групп привычек')
    showDeleteActivity = models.BooleanField(verbose_name='Удаление привычек')
    enableSortTable = models.BooleanField(verbose_name='Перетаскивание привычек')
    enableOpenCloseGroups = models.BooleanField(verbose_name='Открытие/закрытие групп')
    showDeleteAllActivities = models.BooleanField(verbose_name='Кнопка удаления всех привычек')
    onSounds = models.BooleanField(verbose_name='Звуки')
    showRowColumnLight = models.BooleanField(verbose_name='Выделение строки и столбца')
    showActivityDayLight = models.BooleanField(verbose_name='Выделение привычки и дня')
    rowColumnLight = models.CharField(max_length=7, verbose_name='Выделение стоки и столбца')
    fontFamily = models.TextField(verbose_name='Шрифт')
    showOpenAllGroups = models.BooleanField(verbose_name='Открыть/закрыть группы')
    showTabs = models.BooleanField(verbose_name='Проценты')
    selected = models.BooleanField(verbose_name='Выбрана настройка')
    vanishing = models.CharField(max_length=50, verbose_name='Тип исчезновения')

    class Meta:
        verbose_name = 'Настройку'
        verbose_name_plural = 'Настройки'

    def __str__(self):
        return f'Пользователь: {self.user} {self.fontFamily}'
