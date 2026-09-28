/* Live prices for both venues. Endpoints are in live-config.js.
 *
 *   Polymarket sends access-control-allow-origin: *, so the page reads it
 *   directly, once a minute.
 *
 *   Kalshi returns 403 to any browser request, so a server reads it for us.
 *   The page tries each configured endpoint in order: a /api/kalshi function
 *   if one is deployed next to the page, then the file that a scheduled
 *   GitHub Actions job rewrites. An endpoint that answers 404 is not deployed
 *   here and is skipped for the rest of the visit, rather than logging an
 *   error into the console every minute.
 *
 * Live readings do not get a panel of their own. They go to the lead through
 * PA07.lead(), which shows whichever reading is newer for each venue, the
 * build's or the live one, with its own age. On the headline chart the live
 * prices are separate markers past the end of the committed lines.
 */
(function () {
  "use strict";

  var P = window.PA07, C = P.colours, elem = P.elem, CFG = window.PA07_LIVE || {};
  var L = { timer: null, paused: false, pm: null, k: null, pmError: null, kError: null, gone: {} };

  function today() { return new Date().toISOString().slice(0, 10); }

  /* Polymarket seeds unused outcome slots on every event, flagged inactive and
     quoted 0 bid / 1 ask. Anything not active, or closed, or archived, is not
     a market. A bracket with no resting bids has no bestBid field at all
     (omitted, not null), so both sides are tested as finite numbers. */
  function quoted(v) { return v !== null && v !== undefined && isFinite(Number(v)); }
  function live(m) {
    return m && m.active && !m.closed && !m.archived &&
           quoted(m.bestBid) && quoted(m.bestAsk) &&
           !(Number(m.bestBid) === 0 && Number(m.bestAsk) === 1);
  }
  function midOf(m) { return live(m) ? (Number(m.bestBid) + Number(m.bestAsk)) / 2 : null; }

  function fetchJson(url) {
    return fetch(url, { cache: "no-store", mode: "cors" }).then(function (r) {
      if (!r.ok) {
        var err = new Error("HTTP " + r.status + " from " + new URL(r.url, location.href).host);
        err.status = r.status;
        throw err;
      }
      return r.json();
    });
  }

  /* ------------------------------------------------------------- the bar */

  function bar() {
    var host = document.getElementById("livebar");
    if (!host) return;
    var status = elem("span");
    status.id = "livestatus";
    var pause = elem("button", "text", "Pause live prices");
    pause.type = "button";
    pause.setAttribute("aria-pressed", "false");
    pause.addEventListener("click", function () {
      L.paused = !L.paused;
      pause.textContent = L.paused ? "Resume live prices" : "Pause live prices";
      pause.setAttribute("aria-pressed", L.paused ? "true" : "false");
      if (L.paused) { clearTimeout(L.timer); say("Live prices paused."); }
      else tick();
    });
    host.appendChild(status);
    host.appendChild(pause);
  }

  function say(text) {
    var s = document.getElementById("livestatus");
    if (s) s.textContent = text;
  }

  function marginFmt(x) {
    return (x > 0 ? "D+" : x < 0 ? "R+" : "") + Math.abs(x).toFixed(1);
  }

  /* --------------------------------------------------------------- polling */

  function pullPolymarket(d) {
    var cfg = CFG.polymarket || {};
    var points = d.distribution.polymarket_margin.brackets.reduce(function (acc, b) {
      acc[b.bracket] = b.points;
      return acc;
    }, {});
    return Promise.all([fetchJson(cfg.winner_event), fetchJson(cfg.margin_event)])
      .then(function (r) {
        var win = r[0].markets || [], mov = r[1].markets || [];
        function bySlug(slug) {
          /* Slug, never label: Polymarket renamed these outcomes on 10 Sep 2026
             while the slugs held. */
          return win.filter(function (m) { return (m.slug || "").indexOf(slug) >= 0; })[0];
        }
        var out = { at: new Date().toISOString(),
                    pm_dem: midOf(bySlug(cfg.slugs.D)),
                    pm_rep: midOf(bySlug(cfg.slugs.R)) };
        var active = mov.filter(live), total = 0, weighted = 0;
        active.forEach(function (m) {
          var p = points[m.groupItemTitle], q = midOf(m);
          if (p === undefined || q === null) return;
          total += q;
          weighted += q * p;
        });
        /* Normalised before weighting, as the export does it. */
        out.margin = total > 0 ? weighted / total : null;
        return out;
      });
  }

  /* First endpoint that answers with a usable D mid wins. */
  function pullKalshi() {
    var urls = ((CFG.kalshi || {}).endpoints || []).filter(function (u) { return !L.gone[u]; });
    var chain = Promise.reject(new Error("no endpoint configured"));
    urls.forEach(function (u) {
      chain = chain.catch(function () {
        return fetchJson(u).then(function (j) {
          if (!j || !j.D || j.D.mid === null || j.D.mid === undefined) throw new Error("no quote in " + u);
          return { at: j.at, source: j.source, dem: j.D.mid };
        }, function (err) {
          if (err.status === 404) L.gone[u] = true;
          throw err;
        });
      });
    });
    return chain;
  }

  function paint() {
    var shown = P.lead({ pm: L.pm && { v: L.pm.pm_dem, at: L.pm.at },
                         k: L.k && { v: L.k.dem, at: L.k.at } });

    /* The bars stay the build's, so the caption says which number is which. */
    var s = P.state.data.headline.snapshot || {};
    if (L.pm && L.pm.margin !== null) {
      var now = document.getElementById("margin-now"), when = document.getElementById("margin-when");
      if (now) now.textContent = marginFmt(L.pm.margin);
      if (when) when.textContent = " live; the bars are from the last build" +
        (s.expected_margin_pts !== null && s.expected_margin_pts !== undefined
          ? ", when it was " + marginFmt(s.expected_margin_pts) : "");
    }

    var chart = (P.charts || {}).probability;
    if (chart) {
      var marks = [];
      if (shown.pm.live) marks.push({ date: today(), value: shown.pm.v, color: C.D, label: "live" });
      if (shown.k.live) marks.push({ date: today(), value: shown.k.v, color: "#fff", stroke: C.D });
      chart.opts.markers = marks;
      chart.redraw();
    }
  }

  function schedule() {
    clearTimeout(L.timer);
    L.timer = setTimeout(tick, ((CFG.polymarket || {}).poll_seconds || 60) * 1000);
  }

  function tick() {
    var d = P.state.data;
    if (!d || !d.manifest || L.paused) return;
    /* A backgrounded tab should not keep hitting a public API. */
    if (document.hidden) { schedule(); return; }
    var pmDone = pullPolymarket(d).then(function (v) { L.pm = v; L.pmError = null; })
      .catch(function (err) { L.pmError = String(err.message || err); });
    var kDone = pullKalshi().then(function (v) { L.k = v; L.kError = null; })
      .catch(function (err) { L.kError = String(err.message || err); });
    Promise.all([pmDone, kDone]).then(function () {
      paint();
      var t = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
      say(L.pmError && L.kError ? "Live prices could not be read (" + t + "). Showing the last build." :
          L.pmError ? "Polymarket could not be read live (" + L.pmError + ")." :
          "Live prices checked at " + t + ", every " + ((CFG.polymarket || {}).poll_seconds || 60) + " seconds.");
      schedule();
    });
  }

  document.addEventListener("dashboard:ready", function () {
    bar();
    say("Checking live prices…");
    tick();
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && !L.paused) tick();
    });
  });
})();
