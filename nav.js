(function() {
  // Mobile menu toggle. Icons swap via CSS on aria-expanded, since the
  // Font Awesome kit replaces <i> elements with <svg> at load.
  var menuBtn = document.querySelector('.menu-btn');
  if (menuBtn) {
    menuBtn.addEventListener('click', function() {
      var open = menuBtn.closest('header').querySelector('nav').classList.toggle('open');
      menuBtn.setAttribute('aria-expanded', open);
    });
  }

  document.querySelectorAll('.nav-group-btn').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      var group = btn.closest('.nav-group');
      var isOpen = group.classList.contains('open');
      document.querySelectorAll('.nav-group').forEach(function(g) {
        g.classList.remove('open');
        g.querySelector('.nav-group-btn').setAttribute('aria-expanded', 'false');
      });
      if (!isOpen) {
        group.classList.add('open');
        btn.setAttribute('aria-expanded', 'true');
      }
    });
  });
  document.addEventListener('click', function() {
    document.querySelectorAll('.nav-group').forEach(function(g) {
      g.classList.remove('open');
      g.querySelector('.nav-group-btn').setAttribute('aria-expanded', 'false');
    });
  });
})();
