from django.db import migrations


def backfill(apps, schema_editor):
    """Eski arizalar yangi timeline'da to'g'ri ko'rinishi uchun.

    - har bir arizaga "yaratildi" yozuvi (yaratilgan vaqt bilan);
    - mijoz allaqachon baho qoldirgan "yakunlangan" arizalar "tasdiqlandi" bo'ladi
      (yangi oqimda baho = tasdiqlash).
    """
    ServiceRequest = apps.get_model('repair_service', 'ServiceRequest')
    OrderEvent = apps.get_model('repair_service', 'OrderEvent')
    Review = apps.get_model('masters', 'Review')

    reviewed = set(Review.objects.exclude(service_request=None).values_list('service_request_id', flat=True))
    for order in ServiceRequest.objects.all():
        if not OrderEvent.objects.filter(order=order).exists():
            OrderEvent.objects.create(order=order, status='new', actor='customer', created_at=order.created_at)
        if order.status == 'completed' and order.pk in reviewed:
            order.status = 'confirmed'
            order.save(update_fields=['status'])
            OrderEvent.objects.create(order=order, status='confirmed', actor='system',
                                      note="Migratsiya: baho qoldirilgan", created_at=order.updated_at)


class Migration(migrations.Migration):

    dependencies = [
        ('repair_service', '0004_order_workflow'),
        ('masters', '0001_initial'),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
