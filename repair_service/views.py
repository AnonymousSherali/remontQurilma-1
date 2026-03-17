from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import ServiceRequest, Service, Testimonial, Brand
import re


def index(request):
    """Bosh sahifa"""
    context = {
        'services': Service.objects.filter(is_active=True),
        'testimonials': Testimonial.objects.filter(is_published=True)[:6],
        'brands': Brand.objects.filter(is_active=True),
    }
    return render(request, 'index.html', context)


@require_POST
def submit_request(request):
    """Ta'mirlash arizasini qabul qilish"""
    name = request.POST.get('name', '').strip()
    phone = request.POST.get('phone', '').strip()
    email = request.POST.get('email', '').strip()
    problem_description = request.POST.get('problem_description', '').strip()

    # Server tomonida validatsiya
    errors = {}

    if len(name) < 2:
        errors['name'] = 'Ism kamida 2 ta belgidan iborat bo\'lishi kerak'

    if not phone:
        errors['phone'] = 'Telefon raqamni kiriting'
    elif not re.match(r'^\+998\s?\(?\d{2}\)?\s?\d{3}[-\s]?\d{2}[-\s]?\d{2}$', phone):
        errors['phone'] = 'Telefon raqamini to\'g\'ri formatda kiriting: +998 (XX) XXX-XX-XX'

    if email and not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        errors['email'] = 'Email manzilini to\'g\'ri formatda kiriting'

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if errors:
        if is_ajax:
            return JsonResponse({'success': False, 'errors': errors}, status=400)
        return render(request, 'index.html', {
            'errors': errors,
            'services': Service.objects.filter(is_active=True),
            'testimonials': Testimonial.objects.filter(is_published=True)[:6],
            'brands': Brand.objects.filter(is_active=True),
        })

    try:
        service_request = ServiceRequest.objects.create(
            name=name,
            phone=phone,
            email=email or None,
            problem_description=problem_description,
        )

        success_message = 'Arizangiz qabul qilindi! Tez orada siz bilan bog\'lanamiz.'

        if is_ajax:
            return JsonResponse({
                'success': True,
                'message': success_message,
                'request_id': service_request.id,
            })
        return render(request, 'result.html', {'success': True, 'message': success_message})

    except Exception:
        error_message = 'Xatolik yuz berdi. Iltimos, qaytadan urinib ko\'ring yoki qo\'ng\'iroq qiling.'
        if is_ajax:
            return JsonResponse({'success': False, 'message': error_message}, status=500)
        return render(request, 'result.html', {'success': False, 'message': error_message})


def result(request):
    """Ariza yuborish natijasi sahifasi"""
    return render(request, 'result.html', {
        'success': True,
        'message': 'Arizangiz uchun rahmat!',
    })
