from django.contrib.auth.models import User
from django.db import models
from django.forms.models import model_to_dict
from django.conf import settings
from django.core.exceptions import ValidationError
from .preferences import validate_theme_color
try:
    from zoneinfo import ZoneInfo
except ImportError:
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

        from .streaks import users_with_login_streak
        return users_with_login_streak().filter(pk=self.user_id).values_list('login_streak', flat=True).get()

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
    description = models.TextField('Описание', max_length=3000, blank=True, default='')
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
    showStreak = models.BooleanField(default=True, verbose_name='Показывать стрик')
    showTop = models.BooleanField(default=True, verbose_name='Показывать кнопку топа')
    showFeedback = models.BooleanField(default=True, verbose_name='Показывать кнопку обратной связи')
    showCompletedButton = models.BooleanField(default=True, verbose_name='Показывать кнопку выполненных активностей')
    showChat = models.BooleanField(default=True, verbose_name='Показывать кнопку чата')
    showActivityIcons = models.BooleanField(default=True, verbose_name='Показывать иконки привычек и групп')
    showViewSwitch = models.BooleanField(default=True, verbose_name='Показывать переключатель «Таблица / Год»')
    showThemeSchedule = models.BooleanField(default=True, verbose_name='Показывать кнопку расписания тем')
    selected = models.BooleanField(verbose_name='Выбрана настройка')
    vanishing = models.CharField(max_length=50, verbose_name='Тип исчезновения')

    class Meta:
        verbose_name = 'Настройку'
        verbose_name_plural = 'Настройки'

    def __str__(self):
        return f'Пользователь: {self.user} {self.fontFamily}'


class ScheduledTheme(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='scheduled_themes', verbose_name='Владелец')
    name = models.CharField('Название темы', max_length=80)
    rowColumnLight = models.CharField('Выделение строки и столбца', max_length=7, validators=[validate_theme_color])
    backgroundColor = models.CharField('Фон', max_length=7, validators=[validate_theme_color])
    tableHeadColorWeekend = models.CharField('Выходные', max_length=7, validators=[validate_theme_color])
    tableHeadColor = models.CharField('Фон заголовка таблицы', max_length=7, validators=[validate_theme_color])
    tableHeadTextColor = models.CharField('Текст заголовка таблицы', max_length=7, validators=[validate_theme_color])
    activation_time = models.TimeField('Время включения')
    is_enabled = models.BooleanField('Автоматическое включение', default=True)
    # MySQL has no partial unique indexes. NULL allows disabled themes to share a time.
    active_time = models.TimeField(null=True, editable=False)
    created_at = models.DateTimeField('Создана', auto_now_add=True)
    updated_at = models.DateTimeField('Изменена', auto_now=True)

    class Meta:
        ordering = ('activation_time', 'pk')
        verbose_name = 'Тема по расписанию'
        verbose_name_plural = 'Темы по расписанию'
        constraints = [
            models.UniqueConstraint(fields=('user', 'active_time'), name='unique_user_active_theme_time'),
            models.CheckConstraint(
                check=(models.Q(is_enabled=False, active_time__isnull=True) |
                       models.Q(is_enabled=True, active_time__isnull=False, active_time=models.F('activation_time'))),
                name='theme_active_time_matches_schedule'),
        ]

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        self.active_time = self.activation_time if self.is_enabled else None
        if not self.name:
            raise ValidationError({'name': 'Введите название темы.'})
        if self.activation_time and (self.activation_time.second or self.activation_time.microsecond):
            raise ValidationError({'activation_time': 'Укажите время в формате ЧЧ:ММ.'})
        if self.is_enabled and self.activation_time and self.user_id:
            conflict = type(self).objects.filter(user_id=self.user_id, active_time=self.activation_time).exclude(pk=self.pk)
            if conflict.exists():
                raise ValidationError({'activation_time': f'На {self.activation_time:%H:%M} уже назначена другая тема.'})

    def save(self, *args, **kwargs):
        self.active_time = self.activation_time if self.is_enabled else None
        if kwargs.get('update_fields') and {'activation_time', 'is_enabled'} & set(kwargs['update_fields']):
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'active_time'}
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} — {self.activation_time:%H:%M}'


class Feedback(models.Model):
    class Category(models.TextChoices):
        BUG = 'bug', 'Ошибка'
        IDEA = 'idea', 'Предложение'
        THANKS = 'thanks', 'Благодарность'
        OTHER = 'other', 'Другое'

    category = models.CharField('Тип обращения', max_length=10, choices=Category.choices)
    message = models.TextField('Сообщение', max_length=3000)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             null=True, blank=True, verbose_name='Пользователь')
    created_at = models.DateTimeField('Дата отправки', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'Обратная связь'
        verbose_name_plural = 'Обратная связь'

    def __str__(self):
        return f'{self.get_category_display()} — {self.created_at:%d.%m.%Y}'
