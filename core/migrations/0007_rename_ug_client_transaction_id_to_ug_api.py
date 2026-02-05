# Rename ug_client_transaction_id to ug_api in User and SuperSetting (preserves data)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_transaction_order_payload'),
    ]

    operations = [
        migrations.RenameField(
            model_name='user',
            old_name='ug_client_transaction_id',
            new_name='ug_api',
        ),
        migrations.RenameField(
            model_name='supersetting',
            old_name='ug_client_transaction_id',
            new_name='ug_api',
        ),
    ]
