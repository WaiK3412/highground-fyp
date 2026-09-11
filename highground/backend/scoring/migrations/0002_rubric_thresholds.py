from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scoring", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="priorityrubricversion",
            name="high_threshold",
            field=models.PositiveSmallIntegerField(default=70),
        ),
        migrations.AddField(
            model_name="priorityrubricversion",
            name="medium_threshold",
            field=models.PositiveSmallIntegerField(default=40),
        ),
    ]
