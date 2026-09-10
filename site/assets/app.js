/* PA-07 tracker: page boot and the data layer.
 *
 * The site is static: no bundler, no framework, no build step. It fetches the
 * JSON that export_site.py committed and draws it. That constraint is the whole
 * point: it has to work the same served from a laptop today and from GitHub Pages
 * later, with nothing installed in between.
 *
 * All paths are relative so the page does not care whether it is served from a
 * domain root or from /pa07-tracker/site/.
 */
(function () {
  "use strict";

  var D = "#2E5FA3", R = "#C0392B", MODEL = "#6D4C9F", POLL = "#A8620B";

  var State = { data: {} };

  function $(id) { return document.getElementById(id); }

  function elem(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function get(path) {
    return fetch(path, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error(path + " -> HTTP " + r.status);
      return r.json();
    });
  }

  /* ------------------------------------------------------------- formatting */

  function ago(iso) {
    if (!iso) return "unknown";
    var t = Date.parse(iso);
    if (isNaN(t)) return iso;
    var mins = (Date.now() - t) / 60000;
    if (mins < 1.5) return "just now";
    if (mins < 90) return Math.round(mins) + " min ago";
    var h = mins / 60;
    if (h < 36) return Math.round(h) + " h ago";
    var d = h / 24;
    if (d < 45) return Math.round(d) + " days ago";
    return Math.round(d / 30.44) + " months ago";
  }

  function utc(iso) {
    if (!iso) return "";
    var t = Date.parse(iso);
    return isNaN(t) ? iso : new Date(t).toISOString().replace("T", " ").slice(0, 16) + " UTC";
  }

  /* ------------------------------------------------------------- freshness */

  function renderSources(man) {
    var ul = $("sources");
    ul.innerHTML = "";
    man.freshness.forEach(function (f) {
      var li = elem("li", "src");
      li.appendChild(elem("span", "tag " + f.kind, f.kind));
      li.appendChild(elem("b", null, f.label));
      var when = elem("span", "when", ago(f.snapshot_utc));
      li.appendChild(when);
      /* The one-line reason each source is live, frozen or hand-fed lives in
         the tooltip rather than a docs page nobody opens. */
      li.title = f.detail + (f.snapshot_utc ? "\n\nAs of " + utc(f.snapshot_utc) : "") +
                 (f.coverage_through ? "\nCovers through " + f.coverage_through : "") +
                 (f.days ? "\n" + f.days + " days of daily history" : "");
      ul.appendChild(li);
    });
  }

  function renderCountdown(man) {
    var days = man.race.days_to_election;
    $("countdown").textContent =
      (days > 0 ? days + " days to the election" : "Election day has passed") +
      " · 3 November 2026";
    $("built").textContent = "Snapshot built " + utc(man.generated_utc) +
      " · " + Object.keys(man.files).length + " data files";
  }

  /* ------------------------------------------------------------------ boot */

  function fail(err) {
    var box = $("boot");
    if (!box) return;
    box.className = "caveat high";
    box.innerHTML = "<b>Could not load the data files.</b><p>" + String(err) + "</p>" +
      "<p>If you opened this file directly, the browser is blocking the fetch. Serve the " +
      "directory instead: <code>cd site &amp;&amp; /usr/bin/python3 -m http.server 8000</code></p>";
  }

  function boot() {
    Promise.all([
      get("data/manifest.json"),
      get("data/headline.json"),
      get("data/series.json"),
      get("data/distribution.json"),
      get("data/polls.json"),
      get("data/caveats.json"),
      get("data/finance.json")
    ]).then(function (r) {
      State.data = { manifest: r[0], headline: r[1], series: r[2], distribution: r[3],
                     polls: r[4], caveats: r[5], finance: r[6] };
      var man = State.data.manifest;
      renderCountdown(man);
      renderSources(man);
      var boot = $("boot");
      if (boot) boot.remove();
      document.dispatchEvent(new CustomEvent("data:ready", { detail: State.data }));
    }).catch(fail);
  }

  window.PA07 = {
    state: State, get: get, elem: elem, ago: ago, utc: utc,
    colours: { D: D, R: R, MODEL: MODEL, POLL: POLL }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
