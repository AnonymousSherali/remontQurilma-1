/**
 * TechService - UX yaxshilashlar
 *
 * Diqqat: mobil menyu va menyu bo'yicha silliq skroll main.js da bajariladi.
 * Bu yerda ularni takrorlamaymiz, aks holda hodisa ikki marta ishlov beriladi.
 */

(function ($) {
    'use strict';

    // ---------- Toast bildirishnomalari ----------
    var Toast = {
        show: function (message, type, duration) {
            type = type || 'info';
            duration = duration || 3500;

            var $toast = $('<div/>', { 'class': 'toast ' + type, 'role': 'status', text: message });
            $('body').append($toast);

            // Brauzer boshlang'ich holatni chizishi uchun keyingi kadrni kutamiz
            requestAnimationFrame(function () {
                requestAnimationFrame(function () { $toast.addClass('show'); });
            });

            setTimeout(function () {
                $toast.removeClass('show');
                setTimeout(function () { $toast.remove(); }, 300);
            }, duration);
        },
        success: function (m, d) { this.show(m, 'success', d); },
        error: function (m, d) { this.show(m, 'error', d); },
        info: function (m, d) { this.show(m, 'info', d); }
    };

    // ---------- Forma validatsiyasi ----------
    // Diqqat: bu faqat qulaylik uchun. Haqiqiy tekshiruv serverda (views.py).
    var Validator = {
        phoneRe: /^\+998\s?\(?\d{2}\)?\s?\d{3}[-\s]?\d{2}[-\s]?\d{2}$/,
        emailRe: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,

        rules: {
            name: function (v) {
                return v.trim().length >= 2 ? null : 'Ism kamida 2 ta belgidan iborat bo\'lishi kerak';
            },
            phone: function (v) {
                if (!v.trim()) { return 'Telefon raqamni kiriting'; }
                return Validator.phoneRe.test(v.trim())
                    ? null
                    : 'Telefon raqamini to\'g\'ri formatda kiriting: +998 (XX) XXX-XX-XX';
            },
            email: function (v) {
                if (!v.trim()) { return null; } // Email ixtiyoriy
                return Validator.emailRe.test(v.trim()) ? null : 'Email manzilini to\'g\'ri formatda kiriting';
            }
        },

        showError: function ($input, message) {
            $input.addClass('error').removeClass('success').attr('aria-invalid', 'true');
            var $error = $input.siblings('.error-message');
            if (!$error.length) {
                $error = $('<div class="error-message"></div>');
                $input.after($error);
            }
            $error.text(message).addClass('show');
        },

        clearError: function ($input) {
            $input.removeClass('error').attr('aria-invalid', null);
            if ($input.val().trim()) { $input.addClass('success'); }
            $input.siblings('.error-message').removeClass('show');
        },

        checkField: function ($input) {
            var rule = this.rules[$input.attr('name')];
            if (!rule) { return true; }
            var message = rule($input.val() || '');
            if (message) {
                this.showError($input, message);
                return false;
            }
            this.clearError($input);
            return true;
        },

        checkForm: function ($form) {
            var self = this;
            var ok = true;
            $form.find('[name]').each(function () {
                if (!self.checkField($(this))) { ok = false; }
            });
            return ok;
        }
    };

    // ---------- AJAX orqali ariza yuborish ----------
    // Har bir formaning yagona submit ishlovchisi. Inline onsubmit ishlatilmaydi.
    function setupAjaxForms() {
        $('.js-request-form').on('submit', function (event) {
            event.preventDefault();

            var $form = $(this);
            var $button = $form.find('button[type="submit"]');
            var $results = $form.find('.results');

            if ($form.data('submitting')) { return; }

            if (!Validator.checkForm($form)) {
                Toast.error('Formadagi xatolarni to\'g\'rilang');
                return;
            }

            $form.data('submitting', true);
            $button.addClass('loading').prop('disabled', true);
            $results.text('');

            // Yuborish tugagach — muvaffaqiyatli yoki xato — tugmani doim tiklaymiz
            var release = function () {
                $form.data('submitting', false);
                $button.removeClass('loading').prop('disabled', false);
            };

            fetch($form.attr('action'), {
                method: 'POST',
                body: new FormData(this),
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin'
            })
                .then(function (response) {
                    return response.json().then(function (data) {
                        return { ok: response.ok, data: data };
                    });
                })
                .then(function (result) {
                    release();

                    if (result.ok && result.data.success) {
                        onSuccess($form, result.data.message);
                        return;
                    }

                    // Server maydon bo'yicha xatolarni qaytardi
                    if (result.data.errors) {
                        $.each(result.data.errors, function (field, message) {
                            var $input = $form.find('[name="' + field + '"]');
                            if ($input.length) {
                                Validator.showError($input, message);
                            } else {
                                $results.text(message);
                            }
                        });
                        Toast.error('Formadagi xatolarni to\'g\'rilang');
                        return;
                    }

                    var msg = result.data.message || 'Xatolik yuz berdi. Keyinroq urinib ko\'ring.';
                    $results.text(msg);
                    Toast.error(msg);
                })
                .catch(function (error) {
                    release();
                    console.error('Ariza yuborishda xatolik:', error);
                    var msg = 'Tarmoq xatosi. Internetni tekshirib, qaytadan urinib ko\'ring.';
                    $results.text(msg);
                    Toast.error(msg);
                });
        });
    }

    function onSuccess($form, message) {
        clearDraft();
        $form[0].reset();
        $form.find('.form-control').removeClass('success error');
        $form.find('.error-message').removeClass('show');

        Toast.success(message || 'Arizangiz qabul qilindi!', 5000);

        // Modal ichidan yuborilgan bo'lsa — modalni yopamiz
        var $modal = $form.closest('.modal');
        if ($modal.length) { $modal.modal('hide'); }

        // Sahifadagi tasdiq oynasi
        var $confirm = $('.myModal');
        if ($confirm.length) {
            $confirm.show();
            setTimeout(function () { $confirm.hide(); }, 5000);
        }
    }

    // ---------- Maydondan chiqqanda tekshirish ----------
    function setupRealTimeValidation() {
        $('.js-request-form').on('blur', '[name]', function () {
            var $input = $(this);
            if ($input.val() && $input.val().trim()) {
                Validator.checkField($input);
            }
        });

        // Foydalanuvchi tuzatishni boshlasa, xato belgisini olib tashlaymiz
        $('.js-request-form').on('input', '.error', function () {
            $(this).removeClass('error').siblings('.error-message').removeClass('show');
        });
    }

    // ---------- Forma qoralamasi (localStorage) ----------
    var STORAGE_KEY = 'techservice_form_draft';
    // Faqat bu maydonlar saqlanadi. CSRF tokeni hech qachon saqlanmaydi —
    // eskirgan token keyingi yuborishni buzadi va uni saqlash xavfsiz emas.
    var DRAFT_FIELDS = ['name', 'phone', 'email', 'problem_description'];

    function loadDraft() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) { return; }
            var data = JSON.parse(raw);
            DRAFT_FIELDS.forEach(function (field) {
                if (data[field]) {
                    $('.js-request-form').find('[name="' + field + '"]').val(data[field]);
                }
            });
        } catch (e) {
            console.warn('Qoralamani yuklab bo\'lmadi:', e);
        }
    }

    function saveDraft() {
        try {
            var data = {};
            DRAFT_FIELDS.forEach(function (field) {
                var value = $('.js-request-form').find('[name="' + field + '"]')
                    .filter(function () { return !!$(this).val(); })
                    .first().val();
                if (value) { data[field] = value; }
            });
            localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
        } catch (e) {
            console.warn('Qoralamani saqlab bo\'lmadi:', e);
        }
    }

    function clearDraft() {
        try { localStorage.removeItem(STORAGE_KEY); } catch (e) { /* e'tiborsiz */ }
    }

    function setupFormDraft() {
        loadDraft();
        $('.js-request-form').on('change', '[name]', function () {
            if (DRAFT_FIELDS.indexOf($(this).attr('name')) !== -1) { saveDraft(); }
        });
    }

    // ---------- Rasmlarni kechiktirib yuklash ----------
    function setupLazyLoading() {
        var images = document.querySelectorAll('img[data-src]');
        if (!images.length) { return; }

        if (!('IntersectionObserver' in window)) {
            images.forEach(function (img) {
                img.src = img.dataset.src;
                img.classList.add('loaded');
            });
            return;
        }

        var observer = new IntersectionObserver(function (entries, obs) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) { return; }
                var img = entry.target;
                img.src = img.dataset.src;
                img.classList.add('loaded');
                obs.unobserve(img);
            });
        }, { rootMargin: '200px' });

        images.forEach(function (img) { observer.observe(img); });
    }

    // ---------- Modalni Escape bilan yopish ----------
    function setupKeyboardNavigation() {
        $(document).on('keydown', function (event) {
            if (event.key !== 'Escape') { return; }
            $('.modal.in').modal('hide');
            $('.myModal').hide();
        });
    }

    $(document).ready(function () {
        setupAjaxForms();
        setupRealTimeValidation();
        setupFormDraft();
        setupLazyLoading();
        setupKeyboardNavigation();
    });

    window.Toast = Toast;
})(jQuery);
