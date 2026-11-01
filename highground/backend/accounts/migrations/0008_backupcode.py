from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_email_confirmed'),
    ]

    operations = [
        migrations.CreateModel(
            name='BackupCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('salt', models.CharField(max_length=32)),
                ('code_hash', models.CharField(max_length=128)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='backup_codes', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'backup_code',
            },
        ),
    ]
