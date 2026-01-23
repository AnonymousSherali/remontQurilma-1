/**
 * TechService - Optimizatsiyalar
 * Form validation va UX yaxshilash
 */

(function($) {
    'use strict';

    // Toast notification system
    const Toast = {
        show: function(message, type = 'info', duration = 3000) {
            const toast = $('<div class="toast ' + type + '">' + message + '</div>');
            $('body').append(toast);

            setTimeout(() => toast.addClass('show'), 10);

            setTimeout(() => {
                toast.removeClass('show');
                setTimeout(() => toast.remove(), 300);
            }, duration);
        },

        success: function(message, duration) {
            this.show(message, 'success', duration);
        },

        error: function(message, duration) {
            this.show(message, 'error', duration);
        },

        info: function(message, duration) {
            this.show(message, 'info', duration);
        }
    };

    // Form validation
    const FormValidator = {
        // Telefon raqamni tekshirish
        validatePhone: function(phone) {
            // +998 (XX) XXX-XX-XX format
            const phoneRegex = /^\+998\s?\(\d{2}\)\s?\d{3}-\d{2}-\d{2}$/;
            return phoneRegex.test(phone);
        },

        // Emailni tekshirish
        validateEmail: function(email) {
            if (!email) return true; // Email ixtiyoriy
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            return emailRegex.test(email);
        },

        // Ismni tekshirish
        validateName: function(name) {
            return name && name.trim().length >= 2;
        },

        // Muammo tavsifini tekshirish
        validateDescription: function(description) {
            return description && description.trim().length >= 10;
        },

        // Inputga xato ko'rsatish
        showError: function($input, message) {
            $input.addClass('error').removeClass('success');

            let $error = $input.next('.error-message');
            if ($error.length === 0) {
                $error = $('<div class="error-message"></div>');
                $input.after($error);
            }

            $error.text(message).addClass('show');
        },

        // Inputdan xatoni olib tashlash
        clearError: function($input) {
            $input.removeClass('error').addClass('success');
            $input.next('.error-message').removeClass('show');
        },

        // To'liq formani tekshirish
        validateForm: function($form) {
            let isValid = true;
            const self = this;

            // Ism tekshirish
            const $name = $form.find('input[name="name"]');
            if (!this.validateName($name.val())) {
                this.showError($name, 'Iltimos, to\'liq ismingizni kiriting (kamida 2 ta harf)');
                isValid = false;
            } else {
                this.clearError($name);
            }

            // Telefon tekshirish
            const $phone = $form.find('input[name="phone"]');
            if (!this.validatePhone($phone.val())) {
                this.showError($phone, 'Telefon raqamni to\'g\'ri formatda kiriting: +998 (XX) XXX-XX-XX');
                isValid = false;
            } else {
                this.clearError($phone);
            }

            // Email tekshirish (agar to'ldirilgan bo'lsa)
            const $email = $form.find('input[name="email"]');
            if ($email.length && $email.val() && !this.validateEmail($email.val())) {
                this.showError($email, 'Email manzilni to\'g\'ri formatda kiriting');
                isValid = false;
            } else if ($email.length) {
                this.clearError($email);
            }

            // Muammo tavsifi tekshirish
            const $description = $form.find('textarea[name="problem_description"]');
            if ($description.length && !this.validateDescription($description.val())) {
                this.showError($description, 'Muammo haqida batafsil ma\'lumot bering (kamida 10 ta belgi)');
                isValid = false;
            } else if ($description.length) {
                this.clearError($description);
            }

            return isValid;
        }
    };

    // Form yuborish optimizatsiyasi
    function setupFormSubmit() {
        $('form').on('submit', function(e) {
            const $form = $(this);
            const $submitBtn = $form.find('button[type="submit"], .btn_my');

            // Validatsiya
            if (!FormValidator.validateForm($form)) {
                e.preventDefault();
                Toast.error('Formadagi xatolarni to\'g\'rilang');
                return false;
            }

            // Loading holatini ko'rsatish
            $submitBtn.addClass('loading').prop('disabled', true);
        });
    }

    // Real-time validatsiya
    function setupRealTimeValidation() {
        // Ism uchun
        $('input[name="name"]').on('blur', function() {
            const $this = $(this);
            if (!FormValidator.validateName($this.val())) {
                FormValidator.showError($this, 'Iltimos, to\'liq ismingizni kiriting');
            } else {
                FormValidator.clearError($this);
            }
        });

        // Telefon uchun
        $('input[name="phone"]').on('blur', function() {
            const $this = $(this);
            if (!FormValidator.validatePhone($this.val())) {
                FormValidator.showError($this, 'Telefon raqamni to\'g\'ri formatda kiriting');
            } else {
                FormValidator.clearError($this);
            }
        });

        // Email uchun
        $('input[name="email"]').on('blur', function() {
            const $this = $(this);
            if ($this.val() && !FormValidator.validateEmail($this.val())) {
                FormValidator.showError($this, 'Email manzilni to\'g\'ri formatda kiriting');
            } else {
                FormValidator.clearError($this);
            }
        });
    }

    // Lazy loading for images
    function setupLazyLoading() {
        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        img.src = img.dataset.src;
                        img.classList.add('loaded');
                        observer.unobserve(img);
                    }
                });
            });

            document.querySelectorAll('img[data-src]').forEach(img => {
                imageObserver.observe(img);
            });
        } else {
            // Fallback for older browsers
            $('img[data-src]').each(function() {
                $(this).attr('src', $(this).data('src')).addClass('loaded');
            });
        }
    }

    // Smooth scroll to section
    function setupSmoothScroll() {
        $('a[href^="#"]').on('click', function(e) {
            const target = $(this).attr('href');
            if (target && target !== '#' && $(target).length) {
                e.preventDefault();
                const offset = $(window).width() > 992 ? $('.header').height() : 50;
                $('html, body').animate({
                    scrollTop: $(target).offset().top - offset
                }, 500, 'swing');
            }
        });
    }

    // Improved mobile menu
    function setupMobileMenu() {
        $('.mobile-menu').on('click', function() {
            const $menu = $('menu');
            const isOpen = $menu.is(':visible');

            if (isOpen) {
                $menu.slideUp(300);
            } else {
                $menu.slideDown(300);
            }
        });

        // Close menu when clicking on a link
        $('menu a').on('click', function() {
            if ($(window).width() < 992) {
                $('menu').slideUp(300);
                $('.mobile-menu').removeClass('rotate');
            }
        });
    }

    // Form input animation
    function setupInputAnimations() {
        $('.form-control').on('focus', function() {
            $(this).parent().addClass('focused');
        }).on('blur', function() {
            if (!$(this).val()) {
                $(this).parent().removeClass('focused');
            }
        });

        // Check if inputs have values on page load
        $('.form-control').each(function() {
            if ($(this).val()) {
                $(this).parent().addClass('focused');
            }
        });
    }

    // Prevent double submit
    function preventDoubleSubmit() {
        let submitted = false;
        $('form').on('submit', function() {
            if (submitted) {
                return false;
            }
            submitted = true;

            // Reset after 5 seconds (in case of error)
            setTimeout(() => {
                submitted = false;
            }, 5000);
        });
    }

    // Save form data to localStorage (draft)
    function setupFormDraft() {
        const STORAGE_KEY = 'techservice_form_draft';

        // Load draft
        function loadDraft() {
            try {
                const draft = localStorage.getItem(STORAGE_KEY);
                if (draft) {
                    const data = JSON.parse(draft);
                    Object.keys(data).forEach(key => {
                        $(`[name="${key}"]`).val(data[key]);
                    });
                }
            } catch (e) {
                console.log('Draft yuklashda xato:', e);
            }
        }

        // Save draft
        function saveDraft() {
            try {
                const data = {};
                $('form').find('input, textarea, select').each(function() {
                    const name = $(this).attr('name');
                    if (name) {
                        data[name] = $(this).val();
                    }
                });
                localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
            } catch (e) {
                console.log('Draft saqlashda xato:', e);
            }
        }

        // Clear draft
        function clearDraft() {
            localStorage.removeItem(STORAGE_KEY);
        }

        // Load on page load
        loadDraft();

        // Save on input change
        $('form').find('input, textarea, select').on('change', saveDraft);

        // Clear on successful submit
        $('form').on('submit', function() {
            setTimeout(clearDraft, 1000);
        });
    }

    // Keyboard navigation improvements
    function setupKeyboardNavigation() {
        // ESC to close modal
        $(document).on('keydown', function(e) {
            if (e.key === 'Escape') {
                $('.modal').modal('hide');
                $('.myModal').hide();
            }
        });

        // Enter to submit form (except in textarea)
        $('form input').on('keydown', function(e) {
            if (e.key === 'Enter' && !$(this).is('textarea')) {
                e.preventDefault();
                $(this).closest('form').submit();
            }
        });
    }

    // Initialize all optimizations
    $(document).ready(function() {
        setupFormSubmit();
        setupRealTimeValidation();
        setupLazyLoading();
        setupSmoothScroll();
        setupMobileMenu();
        setupInputAnimations();
        preventDoubleSubmit();
        setupFormDraft();
        setupKeyboardNavigation();

        console.log('TechService optimizatsiyalari yuklandi ✓');
    });

    // Make Toast available globally
    window.Toast = Toast;

})(jQuery);
