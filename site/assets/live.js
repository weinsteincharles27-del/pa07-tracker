/* Live prices for both venues.
 *
 *   Polymarket sends access-control-allow-origin: *, so the page reads it
 *   directly, once a minute.
 *
 *   Kalshi returns 403 to any browser request, so a server reads it for us.
 *   The page tries each endpoint listed in manifest.live.kalshi.endpoints in
 *   order: a /api/kalshi function if one is deployed next to the page, then
 *   the file that a GitHub Actions job rewrites every ten minutes. Whatever
 *   answers first wins and its own timestamp is shown, so the age is honest.
 *
 * Live numbers never overwrite the snapshot. Both sit side by side with the
 * difference between them, and on the headline chart the live prices are
 * separate markers past the end of the committed lines.
 */
(function () {
  "use strict";

  var elem = window.PA07.elem, C = window.PA07.colours;
  var L = { timer: null, paused: false, pm: null, k: null, pmError: null, kError: null };

  function pct(v, dp) {
    return v === null || v === undefined ? "n/a" : (v * 100).toFixed(dp === undefined ? 1 : dp) + "%";
  }
  function pp(v) {
    return v === null || v === undefined ? "" :
      (Math.abs(v) < 0.00005 ? "0.0" : (v > 0 ? "+" : "") + (v * 100).toFixed(1)) + " pp";
  }
  function today() { return new Date().toISOString().slice(0, 10); }
  function ago(iso) { return window.PA07.ago(iso); }
  function ageMinutes(iso) { var t = Date.parse(iso || ""); return isNaN(t) ? Infinity : (Date.now() - t) / 60000; }

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
      if (!r.ok) throw new Error("HTTP " + r.status + " from " + new URL(r.url, location.href).host);
      return r.json();
    });
  }

  /* ------------------------------------------------------------- the panel */

  function panel(d) {
    var sec = elem("section", "block");
    sec.id = "livebox";
    var h = elem("header");
    h.appendChild(elem("h2", null, "Live"));
    sec.appendChild(h);
    var body = elem("div");
    body.id = "livebody";
    sec.appendChild(body);

    var controls = elem("div", "controls");
    controls.style.marginTop = "0.75rem";
    var pause = elem("button", null, "Pause");
    pause.addEventListener("click", function () {
      L.paused = !L.paused;
      pause.textContent = L.paused ? "Resume" : "Pause";
      pause.setAttribute("aria-pressed", L.paused ? "true" : "false");
      if (!L.paused) tick();
    });
    var now = elem("button", null, "Refresh");
    now.addEventListener("click", function () { tick(); });
    controls.appendChild(pause);
    controls.appendChild(now);
    var status = elem("span", "small muted");
    status.id = "livestatus";
    controls.appendChild(status);
    sec.appendChild(controls);
    return sec;
  }

  /* One row: label, committed figure, live figure, change, and where the live
     figure came from. `deltaFmt` is separate because the margin row moves in
     margin points, not percentage points. */
  function row(label, snap, now, fmt, deltaFmt, threshold, asOf) {
    var tr = document.createElement("tr");
    var delta = (snap === null || snap === undefined || now === null || now === undefined) ? null : now - snap;
    [label, fmt(snap), now === null || now === undefined ? "waiting" : fmt(now),
     delta === null ? "" : (deltaFmt || pp)(delta), asOf || ""].forEach(function (v, i) {
      var td = document.createElement("td");
      td.textContent = v;
      if (i && i < 4) td.className = "num";
      if (i === 4) td.className = "small muted";
      if (i === 3 && delta !== null && Math.abs(delta) >= (threshold || 0.005)) {
        td.style.color = delta > 0 ? "var(--dem)" : "var(--rep)";
        td.style.fontWeight = "600";
      }
      tr.appendChild(td);
    });
    return tr;
  }

  function marginFmt(x) {
    return x === null || x === undefined ? "n/a" : (x > 0 ? "D+" : x < 0 ? "R+" : "") + Math.abs(x).toFixed(2);
  }

  function render(d) {
    var body = document.getElementById("livebody");
    if (!body) return;
    var s = d.headline.snapshot || {};
    var pm = L.pm || {}, k = L.k || {};
    var kAge = L.k ? ageMinutes(L.k.at) : null;

    var wrap = elem("div", "scroll");
    var t = document.createElement("table");
    var thead = document.createElement("thead"), hr = document.createElement("tr");
    ["", "Last build", "Live", "Change", "As of"].forEach(function (x, i) {
      var th = document.createElement("th");
      th.textContent = x;
      if (i && i < 4) th.className = "num";
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    t.appendChild(thead);
    var tb = document.createElement("tbody");

    var pmWhen = L.pmError ? "poll failed" : (L.pm ? ago(L.pm.at) : "");
    var kWhen = L.kError ? "unavailable" : (L.k ? ago(L.k.at) + (kAge > 45 ? ", stale" : "") : "");

    var rD = row("Brooks (D), Polymarket", s.pm_dem, pm.pm_dem, pct, null, null, pmWhen); rD.className = "d";
    var rK = row("Brooks (D), Kalshi", s.kalshi_dem, k.dem, pct, null, null, kWhen); rK.className = "d";
    tb.appendChild(rD);
    tb.appendChild(rK);
    var cons = pm.pm_dem !== null && pm.pm_dem !== undefined && k.dem !== null && k.dem !== undefined
      ? (pm.pm_dem + k.dem) / 2 : null;
    tb.appendChild(row("Consensus", s.consensus_dem, cons, pct, null, null, ""));
    tb.appendChild(row("Implied margin, Polymarket", s.expected_margin_pts, pm.margin, marginFmt,
      function (x) { return (x > 0 ? "+" : "") + x.toFixed(2) + " pts"; }, 0.005, pmWhen));
    t.appendChild(tb);
    wrap.appendChild(t);
    body.innerHTML = "";
    body.appendChild(wrap);

    var note = elem("p", "fine");
    note.textContent = "Polymarket is read from your browser every " +
      (d.manifest.live.polymarket.poll_seconds || 60) + " seconds. Kalshi is read by a server" +
      (L.k && L.k.source === "vercel" ? " on request." : " every ten minutes.") +
      (L.pmError ? " Polymarket: " + L.pmError + "." : "") +
      (L.kError ? " Kalshi: " + L.kError + "." : "");
    body.appendChild(note);
  }

  function status(text) {
    var s = document.getElementById("livestatus");
    if (s) s.textContent = text;
  }

  /* --------------------------------------------------------------- polling */

  function pullPolymarket(d) {
    var cfg = d.manifest.live.polymarket;
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
  function pullKalshi(d) {
    var cfg = d.manifest.live.kalshi || {}, urls = cfg.endpoints || [];
    var chain = Promise.reject(new Error("no endpoint configured"));
    urls.forEach(function (u) {
      chain = chain.catch(function () {
        return fetchJson(u).then(function (j) {
          if (!j || !j.D || j.D.mid === null || j.D.mid === undefined) throw new Error("no quote in " + u);
          return { at: j.at, source: j.source, dem: j.D.mid, rep: j.R ? j.R.mid : null,
                   bid: j.D.yes_bid, ask: j.D.yes_ask };
        });
      });
    });
    return chain;
  }

  function paint(d) {
    render(d);
    var chart = (window.PA07.charts || {}).probability;
    if (chart) {
      var marks = [];
      if (L.pm && L.pm.pm_dem !== null) marks.push({ date: today(), value: L.pm.pm_dem, color: C.D, label: "live" });
      if (L.k && L.k.dem !== null) marks.push({ date: today(), value: L.k.dem, color: "#fff", stroke: C.D });
      chart.opts.markers = marks;
      chart.redraw();
    }
    var pmChip = document.querySelector('#sources .src[data-id="polymarket"] .when');
    if (pmChip) pmChip.textContent = L.pmError ? "live poll failed" : "live, " + ago(L.pm && L.pm.at);
    var kChip = document.querySelector('#sources .src[data-id="kalshi"] .when');
    if (kChip && (L.k || L.kError)) kChip.textContent = L.kError ? "live read failed" : "live, " + ago(L.k.at);
  }

  function schedule(d) {
    clearTimeout(L.timer);
    var secs = d.manifest.live.polymarket.poll_seconds || 60;
    L.timer = setTimeout(tick, secs * 1000);
  }

  function tick() {
    var d = window.PA07.state.data;
    if (!d || !d.manifest) return;
    if (L.paused) { status("Paused."); return; }
    /* A backgrounded tab should not keep hitting a public API. */
    if (document.hidden) { schedule(d); return; }
    status("Polling...");
    var pmDone = pullPolymarket(d).then(function (v) { L.pm = v; L.pmError = null; })
      .catch(function (err) { L.pmError = String(err.message || err); });
    var kDone = pullKalshi(d).then(function (v) { L.k = v; L.kError = null; })
      .catch(function (err) { L.kError = String(err.message || err); });
    Promise.all([pmDone, kDone]).then(function () {
      paint(d);
      status((L.pmError && L.kError ? "Both reads failed." : "Updated ") + new Date().toLocaleTimeString());
      schedule(d);
    });
  }

  document.addEventListener("dashboard:ready", function (ev) {
    var d = ev.detail, main = document.getElementById("main");
    var probability = document.getElementById("probability");
    var box = panel(d);
    if (probability) main.insertBefore(box, probability);
    else main.appendChild(box);
    render(d);
    tick();
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && !L.paused) tick();
    });
  });
})();
