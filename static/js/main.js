$(document).ready(function() {
	new WOW().init();

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

  // Mobil menyuda havola bosilganda menyuni yopamiz
  $('#top-menu a').click(function() {
    if ($(window).width() < 992) {
      $('.mobile-menu').removeClass('rotate');
      $('menu').slideUp();
    }
  });

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
// Yandex xaritasi. Xarita bloki yoki API mavjud bo'lmasa, jimgina o'tkazib yuboriladi.
var myMap;

function initMap() {
    var el = document.getElementById('map');
    if (!el) { return; }

    var lat = parseFloat(el.dataset.lat) || 41.311151;
    var lng = parseFloat(el.dataset.lng) || 69.279737;
    var pin = el.dataset.pin || '';
    var coords = [lat, lng];

    myMap = new ymaps.Map('map', {
        center: coords,
        zoom: 16,
        controls: ['zoomControl']
    });

    myMap.behaviors.disable(['drag', 'scrollZoom']);

    var pinOptions = pin ? {
        iconLayout: 'default#image',
        iconImageHref: pin,
        iconImageSize: [60, 64],
        iconImageOffset: [-25, -70]
    } : {};

    var collection = new ymaps.GeoObjectCollection({}, pinOptions);
    collection.add(new ymaps.Placemark(coords, {
        balloonContentHeader: 'TechService',
        balloonContentBody: "Toshkent shahar"
    }));

    myMap.geoObjects.add(collection);
}

if (typeof ymaps !== 'undefined' && document.getElementById('map')) {
    ymaps.ready(initMap);
}
