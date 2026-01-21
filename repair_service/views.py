from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import ServiceRequest, Service, Testimonial, Brand
import json


def index(request):
    """Главная страница"""
    context = {
        'services': Service.objects.filter(is_active=True),
        'testimonials': Testimonial.objects.filter(is_published=True)[:6],
        'brands': Brand.objects.filter(is_active=True),
    }
    return render(request, 'index.html', context)


@require_POST
def submit_request(request):
    """Обработка заявки на ремонт"""
    try:
        # Получаем данные из POST запроса
        name = request.POST.get('name', '')
        phone = request.POST.get('phone', '')
        email = request.POST.get('email', '')
        problem = request.POST.get('problem', '')

        # Создаем заявку
        service_request = ServiceRequest.objects.create(
            name=name,
            phone=phone,
            email=email,
            problem_description=problem,
        )

        # Возвращаем успешный ответ
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # Если это AJAX запрос
            return JsonResponse({
                'success': True,
                'message': 'Ваша заявка принята! Мы свяжемся с вами в ближайшее время.',
                'request_id': service_request.id
            })
        else:
            # Если это обычный POST запрос
            return render(request, 'result.html', {
                'success': True,
                'message': 'Ваша заявка принята! Мы свяжемся с вами в ближайшее время.'
            })

    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'message': 'Произошла ошибка. Попробуйте позже или позвоните нам.'
            }, status=400)
        else:
            return render(request, 'result.html', {
                'success': False,
                'message': 'Произошла ошибка. Попробуйте позже или позвоните нам.'
            })


def result(request):
    """Страница результата отправки формы"""
    return render(request, 'result.html', {
        'success': True,
        'message': 'Спасибо за вашу заявку!'
    })
