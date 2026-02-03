# Generated migration for Transaction.order_payload (order-only-after-payment flow)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_order_table_no_optional'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='order_payload',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
