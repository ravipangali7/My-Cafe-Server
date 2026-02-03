# Generated migration for making Order.table_no optional

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_whatsapp_notification_and_settings'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='table_no',
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
    ]
