from django.contrib.auth.models import User
from django.db import models
from django.forms.models import model_to_dict


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
    backgroundColor = models.CharField(max_length=7, verbose_name='Цвет сайта')
    tableHeadColorWeekend = models.CharField(max_length=7, verbose_name='Цвет выходных')
    tableHeadColor = models.CharField(max_length=7, verbose_name='Цвет заголовка таблицы')
    tableHeadTextColor = models.CharField(max_length=7, verbose_name='Цвет текста заголовка таблицы')
    showCalendar = models.BooleanField(verbose_name='Показать календарь')
    showCreateActivity = models.BooleanField(verbose_name='Показать создание активности')
    showCreateActivityGroup = models.BooleanField(verbose_name='Показать создание группы активностей')
    showDeleteActivity = models.BooleanField(verbose_name='Показать удаление активностей')
    enableSortTable = models.BooleanField(verbose_name='Включить перетаскивание строк')
    enableOpenCloseGroups = models.BooleanField(verbose_name='Включить открытие/закрытие групп')
    showDeleteAllActivities = models.BooleanField(verbose_name='Показать кнопку удаления всех активностей')
    onSounds = models.BooleanField(verbose_name='Включить звуки')
    showRowColumnLight = models.BooleanField(verbose_name='Включить выделение строки и столбца')
    showActivityDayLight = models.BooleanField(verbose_name='Включить выделение активности и дня')
    rowColumnLight = models.CharField(max_length=7, verbose_name='Цвет выделения стоки и столбца')
    fontFamily = models.TextField(verbose_name='Шрифт')
    showOpenAllGroups = models.BooleanField(verbose_name='Открыть/закрыть группы')
    showTabs = models.BooleanField(verbose_name='Вкладки')
    selected = models.BooleanField(verbose_name='Выбрана настройка')

    class Meta:
        verbose_name = 'Настройку'
        verbose_name_plural = 'Настройки'

    def __str__(self):
        return f'Пользователь: {self.user} {self.fontFamily}'
