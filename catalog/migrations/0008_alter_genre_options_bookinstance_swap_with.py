# Generated by Django 4.2.1 on 2023-06-06 13:09

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalog", "0007_remove_book_type_bookinstance_type"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="genre",
            options={"ordering": ["name"]},
        ),
        migrations.AddField(
            model_name="bookinstance",
            name="swap_with",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
