# Generated for Online/Offline (Restaurant Open/Closed) feature

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_transaction_nepal_merchant_txn_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='is_online',
            field=models.BooleanField(default=True),
        ),
    ]
