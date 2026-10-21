// Light / dark theme for every page. Loaded in <head>, before the body is drawn, so the page
// never flashes the wrong colours. The choice is kept per browser; until someone picks one,
// the page follows the device setting. Any button with data-theme-toggle switches it.
(function () {
  var KEY = 'inreal-theme';
  var root = document.documentElement;
  var media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function saved() {
    try { var v = localStorage.getItem(KEY); return v === 'dark' || v === 'light' ? v : null; } catch (e) { return null; }
  }
  function current() { return saved() || (media && media.matches ? 'dark' : 'light'); }

  function apply(theme) {
    var dark = theme === 'dark';
    root.classList.toggle('dark', dark);
    root.style.colorScheme = theme;
    var label = dark ? 'Switch to light theme' : 'Switch to dark theme';
    document.querySelectorAll('[data-theme-toggle]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(dark));
      b.setAttribute('aria-label', label);
      b.title = label;
    });
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', dark ? '#0B0F17' : '#FFFDF7');
  }

  // the new theme spreads out in a circle from the button (where the browser supports it)
  function switchTo(theme, x, y) {
    try { localStorage.setItem(KEY, theme); } catch (e) { /* private window: still switch */ }
    if (reduce || !document.startViewTransition) return apply(theme);
    var r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
    var vt = document.startViewTransition(function () { apply(theme); });
    vt.ready.then(function () {
      root.animate({ clipPath: ['circle(0px at ' + x + 'px ' + y + 'px)', 'circle(' + r + 'px at ' + x + 'px ' + y + 'px)'] },
        { duration: 600, easing: 'cubic-bezier(.16, 1, .3, 1)', pseudoElement: '::view-transition-new(root)' });
    }).catch(function () {});
  }

  apply(current());
  if (media) {
    var follow = function () { if (!saved()) apply(current()); };
    if (media.addEventListener) media.addEventListener('change', follow); else if (media.addListener) media.addListener(follow);
  }
  document.addEventListener('DOMContentLoaded', function () { apply(current()); });
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-theme-toggle]');
    if (!b) return;
    var box = b.getBoundingClientRect();
    switchTo(current() === 'dark' ? 'light' : 'dark', box.left + box.width / 2, box.top + box.height / 2);
  });
  window.InRealTheme = { get: current, set: function (t) { switchTo(t, innerWidth - 40, 30); } };
})();
