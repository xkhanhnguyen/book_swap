# Generated by Django 4.2.1 on 2023-06-14 16:36

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0009_alter_bookinstance_options_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="author",
            name="date_of_death",
        ),
    ]
