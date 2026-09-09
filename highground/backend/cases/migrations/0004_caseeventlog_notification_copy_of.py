import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0003_alter_casephoto_file_path"),
    ]

    operations = [
        migrations.AddField(
            model_name="caseeventlog",
            name="notification_copy_of",
            field=models.ForeignKey(
                blank=True,
                help_text="Canonical event when this row only stores another recipient's read state.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="notification_copies",
                to="cases.caseeventlog",
            ),
        ),
    ]
