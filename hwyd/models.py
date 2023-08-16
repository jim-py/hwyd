from django.db import models


class ActivitiesConnection(models.Model):
    group = models.ForeignKey('Activities', on_delete=models.CASCADE, verbose_name='Группа', related_name='group')
    activity = models.ForeignKey('Activities', on_delete=models.CASCADE, verbose_name='Активность', related_name='activity')

    def __str__(self):
        return f'{self.activity}'


class Activities(models.Model):
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

    class Meta:
        verbose_name = 'Активность'
        verbose_name_plural = 'Активности'
        ordering = ['number']

    def __str__(self):
        return f'{self.name}'


class Settings(models.Model):
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

    class Meta:
        verbose_name = 'Настройку'
        verbose_name_plural = 'Настройки'
