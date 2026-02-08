# Generated for Order type, address, and payment method

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_user_is_online'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='order_type',
            field=models.CharField(
                choices=[('table', 'Table'), ('packing', 'Packing'), ('delivery', 'Delivery')],
                default='table',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='address',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AddField(
            model_name='order',
            name='payment_method',
            field=models.CharField(
                choices=[('cash', 'Cash'), ('online', 'Online')],
                default='online',
                max_length=20,
            ),
        ),
    ]
