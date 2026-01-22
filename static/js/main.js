$(document).ready(function() {
	new WOW().init();

	$('.hiden').hide();
	$('.users').click(function() {
		$('.bottom').toggleClass('open');
		$('.hiden').slideToggle().show();
	});

	$('.services .last span').hide();

	$('.services .inside button').click(function() {
		$(this).toggleClass('rotate');
		$(this).parent().find('.last').toggleClass('open');
		$(this).parent().find('.last span').slideToggle();
		$(this).parent().find('.dots').toggleClass('dots-hide');
	});

	$('.myModal .close').click(function() {
		$('.myModal').hide();
		$('html').removeClass('send_done');
	});


  $('.mobile-menu').click(function() {
    $(this).toggleClass('rotate');
    $('menu').slideToggle();
  });

	$(window).scroll(function () {
	    var sc = $(window).scrollTop()
	    if (sc > 200) {
	        $(".main-content .bg").addClass("enabled");
	    } else {
	        $(".main-content .bg").removeClass("enabled");
	    }
	});
  // $(window).resize(function(){
  //   if( $(document).width() < 992 ) {
  //     if($(window).scrollTop() > 100){
  //       $('header').addClass('enabled');
  //     }
  //     $('menu').addClass('menuTrigger');
  //     MenuPosition();
  //   }else{
  //     $('#top-menu').removeAttr('style');
  //     $('header').css('position', 'relative').removeAttr('class');
  //     $('menu').removeClass('menuTrigger');
  //     $('.top-bar').removeAttr('style');
  //   }
  // })
  // if( $(document).width() < 992 ) {
  //     if($(window).scrollTop() > 100){
  //       $('header').addClass('enabled');
  //     }
  //     $('menu').addClass('menuTrigger');
  //     MenuPosition();
  //   }else{
  //     $('#top-menu').removeAttr('style');
  //     $('header').css('position', 'relative').removeAttr('class');
  //     $('menu').removeClass('menuTrigger');
  //     $('.top-bar').removeAttr('style');
  //   }
  function MenuPosition(){
      $(document).on('click','.menuTrigger li', function() {
        //$('.menuTrigger li').removeClass('active');
        $('.mobile-menu').removeClass('rotate');
        $('menu').slideUp();
      });

      $(window).scroll(function () {
        var sc = $(window).scrollTop()
        if (sc > 100) {
            $("header").addClass("enabled");
        } else {
            $("header").removeClass("enabled");
        }
      });
      $('header').removeAttr('style');
  }

	$(window).scroll(function () {
	    var sc = $(window).scrollTop()
	    if (sc > 440) {
	        $(".main-content .bg").addClass("enabled");
	    } else {
	        $(".main-content .bg").removeClass("enabled");
	    }
	});

  // browser window scroll (in pixels) after which the "back to top" link is shown
  var offset = 300,
    //browser window scroll (in pixels) after which the "back to top" link opacity is reduced
    offset_opacity = 1200,
    //duration of the top scrolling animation (in ms)
    scroll_top_duration = 700,
    //grab the "back to top" link
    $back_to_top = $('.cd-top');

  //hide or show the "back to top" link
  $(window).scroll(function(){
    ( $(this).scrollTop() > offset ) ? $back_to_top.addClass('cd-is-visible') : $back_to_top.removeClass('cd-is-visible cd-fade-out');
    if( $(this).scrollTop() > offset_opacity ) {
      $back_to_top.addClass('cd-fade-out');
    }
  });

  //smooth scroll to top
  $back_to_top.on('click', function(event){
    event.preventDefault();
    $('body,html').animate({
      scrollTop: 0 ,
      }, scroll_top_duration
    );
  });
   $(function() {
            $("input[name='phone']").mask('+998 (99) 999-99-99');

            // Contents of textboxes will be selected when receiving focus.
            $("input[type=text]")
                .focus(function() {
                    $(this).select();
                });
        });
});

// Cache selectors
var lastId,
    topMenu = $("#top-menu"),
    topMenuHeight = topMenu.height() + $('.top-bar').height() + 100;
    // All list items
    menuItems = topMenu.find("a"),
    // Anchors corresponding to menu items
    scrollItems = menuItems.map(function(){
      var item = $($(this).attr("href"));
      if (item.length) { return item; }
    });

// Bind click handler to menu items
// so we can get a fancy scroll animation
menuItems.click(function(e){
  var $menu_id = $(this).attr('href')
   if( $(document).width() > 992 ) {
    $('html, body').animate({
        scrollTop: $($menu_id).offset().top - $('.header').height()
    }, 300);
  }else{
        $('html, body').animate({
        scrollTop: $($menu_id).offset().top - 50
    }, 300);
  }
});

// Bind to scroll
$(window).scroll(function(){
   // Get container scroll position
   if( $(window).width() > 992 ) {
    var fromTop = $(document).scrollTop()-topMenuHeight + 500;
    }else{
      var fromTop = $(document).scrollTop()-topMenuHeight + 1000;
    }

   // Get id of current scroll item
   var cur = scrollItems.map(function(){
     if ($(this).offset().top < fromTop)
       return this;
   });
   // Get the id of the current element
   cur = cur[cur.length-1];
   var id = cur && cur.length ? cur[0].id : "";

   //if (lastId !== id) {
       lastId = id;
       // Set/remove active class
       menuItems
         .parent().removeClass("active")
         $("[href='#"+id+"']").parent().addClass("active");
   //}
});
ymaps.ready(init);
var myMap;

function init(){
    myMap = new ymaps.Map ("map", {
        center: [41.311151, 69.279737],
        zoom: 16
    });

    myMap.controls.remove('searchControl').remove('trafficControl').remove('geolocationControl');

    myMap.behaviors.disable(['drag', 'scrollZoom']);

    myPin = new ymaps.GeoObjectCollection({}, {
      iconLayout: 'default#image',
      iconImageHref: 'img/pointer23.svg',
      iconImageSize: [60, 64],
      iconImageOffset: [-25, -70]
    });

    myPlacemark1 = new ymaps.Placemark([41.311151, 69.279737], {
      balloonContentHeader: '<img src="img/pointer23.svg" class="mc__logo">',
    });


    myPin.add(myPlacemark1);

    myMap.geoObjects.add(myPin);
}
