# Generated by Django 4.2.4 on 2023-12-30 04:57

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hwyd', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customfieldsuser',
            name='lastActive',
            field=models.DateTimeField(default=datetime.datetime(2023, 12, 30, 7, 57, 22, 969784)),
        ),
    ]
