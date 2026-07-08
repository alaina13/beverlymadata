(function() {
  var toc = document.querySelector('.toc');
  if (!toc) return;
  var links = Array.prototype.slice.call(toc.querySelectorAll('.toc-link'));
  if (!links.length) return;
  var targets = links.map(function(link) {
    return document.getElementById(link.getAttribute('href').slice(1));
  });

  function setActive(link) {
    links.forEach(function(l) { l.classList.remove('active'); });
    if (link) link.classList.add('active');
  }

  var observer = new IntersectionObserver(function(entries) {
    entries.forEach(function(entry) {
      if (entry.isIntersecting) {
        var idx = targets.indexOf(entry.target);
        if (idx !== -1) setActive(links[idx]);
      }
    });
  }, { rootMargin: '-80px 0px -75% 0px', threshold: 0 });

  targets.forEach(function(t) { if (t) observer.observe(t); });
  setActive(links[0]);

  // Fallback: if the last section is too short to reach the detection zone
  // near the top, force it active once the user hits the bottom of the page.
  window.addEventListener('scroll', function() {
    var atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
    if (atBottom) setActive(links[links.length - 1]);
  }, { passive: true });
})();
