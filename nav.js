(function() {
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
