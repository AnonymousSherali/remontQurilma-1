import uuid

from django.db import migrations, models


def fill_tokens(apps, schema_editor):
    """Mavjud har bir arizaga alohida baho kaliti beriladi.

    To'g'ridan-to'g'ri `unique=True, default=uuid4` qo'shilsa, Django barcha
    eski qatorlarga BIR XIL qiymat yozadi va migratsiya unique xatosi bilan yiqiladi.
    """
    ServiceRequest = apps.get_model('repair_service', 'ServiceRequest')
    for request in ServiceRequest.objects.filter(review_token__isnull=True).only('pk'):
        request.review_token = uuid.uuid4()
        request.save(update_fields=['review_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('repair_service', '0002_platform_fields'),
    ]

    operations = [
        migrations.RunPython(fill_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='servicerequest',
            name='review_token',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name='Baho kaliti'),
        ),
    ]
