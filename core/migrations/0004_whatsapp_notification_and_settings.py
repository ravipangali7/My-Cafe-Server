# Generated manually for WhatsApp Notifications feature

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_vendorcustomer'),
    ]

    operations = [
        migrations.AddField(
            model_name='supersetting',
            name='whatsapp_template_imagemarketing',
            field=models.CharField(blank=True, default='mycafeimagemarketing', max_length=100),
        ),
        migrations.AddField(
            model_name='supersetting',
            name='whatsapp_template_marketing',
            field=models.CharField(blank=True, default='mycafemarketing', max_length=100),
        ),
        migrations.CreateModel(
            name='WhatsAppNotification',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('message', models.TextField()),
                ('image', models.ImageField(blank=True, null=True, upload_to='whatsapp_notifications/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('sending', 'Sending'),
                        ('sent', 'Sent'),
                        ('failed', 'Failed'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('sent_count', models.PositiveIntegerField(default=0)),
                ('total_count', models.PositiveIntegerField(default=0)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='whatsapp_notifications',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('customers', models.ManyToManyField(
                    blank=True,
                    related_name='whatsapp_notifications',
                    to='core.vendorcustomer',
                )),
            ],
            options={
                'verbose_name': 'WhatsApp Notification',
                'verbose_name_plural': 'WhatsApp Notifications',
                'ordering': ['-created_at'],
            },
        ),
    ]
