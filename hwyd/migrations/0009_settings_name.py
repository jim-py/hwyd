# Generated by Django 4.2.4 on 2023-09-26 05:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hwyd', '0008_activities_hide_settings_selected'),
    ]

    operations = [
        migrations.AddField(
            model_name='settings',
            name='name',
            field=models.CharField(default='', max_length=100, verbose_name='Название'),
            preserve_default=False,
        ),
    ]
