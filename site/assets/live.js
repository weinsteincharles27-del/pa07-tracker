/* Live Polymarket polling, and being honest about what "live" covers.
 *
 * Exactly one of the two venues can be read from a web page.
 *
 *   Polymarket answers gamma-api and clob requests with
 *   access-control-allow-origin: *, so a browser can fetch it directly and
 *   this page does, on an interval, with no server in between.
 *
 *   Kalshi sends no CORS header at all, answers the preflight with a bare 403,
 *   and requires every request to be signed with an RSA-PSS private key. There
 *   is no arrangement under which a public static page can call it. Everything
 *   Kalshi here is as of the last scheduled build, and this panel says so in
 *   the same table as the live figures rather than in a footnote.
 *
 * The live numbers never overwrite the snapshot. Both are shown side by side
 * with the difference between them, because a page that quietly replaces a
 * committed figure with a fresher one has destroyed the reader's ability to
 * tell which parts of the page are which. On the headline chart the live price
 * is a separate marker sitting past the end of the committed line, for the same
 * reason.
 */
(function () {
  "use strict";

  var elem = window.PA07.elem, C = window.PA07.colours;
  var L = { timer: null, paused: false, last: null, error: null, tries: 0 };

  function pct(v, dp) {
    return v === null || v === undefined ? "n/a" : (v * 100).toFixed(dp === undefined ? 1 : dp) + "%";
  }
  function pp(v) {
    return v === null || v === undefined ? "" :
      (Math.abs(v) < 0.00005 ? "0.0" : (v > 0 ? "+" : "") + (v * 100).toFixed(1)) + " pp";
  }
  function today() { return new Date().toISOString().slice(0, 10); }

  /* Polymarket seeds unused outcome slots on every event: markets named "A",
     "B", "Person A", "Other", flagged inactive and quoted 0 bid / 1 ask because
     nothing rests on either side. Averaging those in would put the whole book at
     50%. Anything not active, or closed, or archived, is not a market. */
  function live(m) {
    return m && m.active && !m.closed && !m.archived &&
           m.bestBid !== null && m.bestAsk !== null &&
           !(Number(m.bestBid) === 0 && Number(m.bestAsk) === 1);
  }

  function midOf(m) {
    return live(m) ? (Number(m.bestBid) + Number(m.bestAsk)) / 2 : null;
  }

  function fetchJson(url) {
    return fetch(url, { cache: "no-store", mode: "cors" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status + " from " + new URL(url).host);
      return r.json();
    });
  }

  /* ------------------------------------------------------------- the panel */

  /* `deltaFmt` is a separate argument on purpose. The probability rows move in
     percentage points and the margin row moves in margin points, and running
     both through one formatter turned a 0.73-point move in the implied margin
     into "+72.7 pp". */
  function row(label, snap, now, fmt, deltaFmt, threshold) {
    var tr = document.createElement("tr");
    var delta = (snap === null || snap === undefined || now === null || now === undefined)
      ? null : now - snap;
    [label, fmt(snap), now === null || now === undefined ? "waiting" : fmt(now),
     delta === null ? "" : (deltaFmt || pp)(delta)].forEach(function (v, i) {
      var td = document.createElement("td");
      td.textContent = v;
      if (i) td.className = "num";
      if (i === 3 && delta !== null && Math.abs(delta) >= (threshold || 0.005)) {
        td.style.color = delta > 0 ? "var(--dem)" : "var(--rep)";
        td.style.fontWeight = "600";
      }
      tr.appendChild(td);
    });
    return tr;
  }

  function panel(d) {
    var sec = elem("section", "block");
    sec.id = "livebox";
    var h = elem("header");
    h.appendChild(elem("h2", null, "Live against the last committed snapshot"));
    h.appendChild(elem("p", null,
      "One of the two venues can be read from a web page. This panel polls it every " +
      (d.manifest.live.polymarket.poll_seconds) + " seconds from your browser and puts the " +
      "result next to the figure this page was built with, so you can see which is which."));
    sec.appendChild(h);

    var body = elem("div");
    body.id = "livebody";
    sec.appendChild(body);

    var controls = elem("div", "controls");
    controls.style.marginTop = "0.75rem";
    var pause = elem("button", null, "Pause polling");
    pause.addEventListener("click", function () {
      L.paused = !L.paused;
      pause.textContent = L.paused ? "Resume polling" : "Pause polling";
      pause.setAttribute("aria-pressed", L.paused ? "true" : "false");
      if (!L.paused) tick();
    });
    var now = elem("button", null, "Refresh now");
    now.addEventListener("click", function () { tick(); });
    controls.appendChild(pause);
    controls.appendChild(now);
    var status = elem("span", "small muted");
    status.id = "livestatus";
    controls.appendChild(status);
    sec.appendChild(controls);
    return sec;
  }

  function render(d) {
    var body = document.getElementById("livebody");
    if (!body) return;
    var s = d.headline.snapshot || {};
    var dist = d.distribution.polymarket_margin;
    var v = L.last || {};

    var wrap = elem("div", "scroll");
    var t = document.createElement("table");
    var thead = document.createElement("thead");
    var hr = document.createElement("tr");
    ["", "Last build", "Live now", "Change"].forEach(function (x, i) {
      var th = document.createElement("th");
      th.textContent = x;
      if (i) th.className = "num";
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    t.appendChild(thead);
    var tb = document.createElement("tbody");

    var rD = row("Brooks (D), Polymarket", s.pm_dem, v.pm_dem, pct); rD.className = "d";
    var rR = row("Mackenzie (R), Polymarket", s.pm_rep, v.pm_rep, pct); rR.className = "r";
    tb.appendChild(rD);
    tb.appendChild(rR);
    tb.appendChild(row("Market-implied margin", s.expected_margin_pts, v.margin,
      function (x) {
        return x === null || x === undefined ? "n/a"
          : (x > 0 ? "D+" : x < 0 ? "R+" : "") + Math.abs(x).toFixed(2);
      },
      function (x) { return (x > 0 ? "+" : "") + x.toFixed(2) + " pts"; }, 0.005));

    /* Kalshi gets a row in the same table, with its cells struck out rather
       than left blank. A blank reads as "no data yet"; this is "no data ever,
       from here". */
    var k = document.createElement("tr");
    [["Brooks (D), Kalshi", pct(s.kalshi_dem), "cannot be polled from a page", ""]]
      .forEach(function (cells) {
        cells.forEach(function (val, i) {
          var td = document.createElement("td");
          td.textContent = val;
          if (i) td.className = "num";
          if (i === 2) { td.className = "gap"; td.title = d.manifest.live.kalshi.why; }
          k.appendChild(td);
        });
      });
    tb.appendChild(k);
    t.appendChild(tb);
    wrap.appendChild(t);
    body.innerHTML = "";
    body.appendChild(wrap);

    var when = elem("p", "small muted");
    when.style.marginTop = "0.6rem";
    when.innerHTML = L.error
      ? "<b>The last poll failed:</b> " + L.error + ". Showing " +
        (L.last ? "the last live figures, from " + window.PA07.ago(L.last.at) + "."
                : "the committed snapshot only.")
      : (L.last
          ? "Live figures polled directly from gamma-api.polymarket.com, " +
            window.PA07.ago(L.last.at) + ", from " + L.last.brackets +
            " active margin brackets. Nothing on this page is written back anywhere; " +
            "reload and you are looking at the committed snapshot again."
          : "Polling Polymarket now.");
    body.appendChild(when);

    if (dist && v.brackets && v.brackets !== dist.brackets.length) {
      var warn = elem("div", "caveat medium");
      warn.innerHTML = "<b>The margin ladder changed shape.</b><p>The committed snapshot has " +
        dist.brackets.length + " active brackets and Polymarket is returning " + v.brackets +
        " right now. A bracket was added, retired or renamed since the last build.</p>";
      body.appendChild(warn);
    }
  }

  function status(text) {
    var s = document.getElementById("livestatus");
    if (s) s.textContent = text;
  }

  /* --------------------------------------------------------------- polling */

  function pull(d) {
    var cfg = d.manifest.live.polymarket;
    var points = d.distribution.polymarket_margin.brackets.reduce(function (acc, b) {
      acc[b.bracket] = b.points;
      return acc;
    }, {});

    return Promise.all([fetchJson(cfg.winner_event), fetchJson(cfg.margin_event)])
      .then(function (r) {
        var win = r[0].markets || [], mov = r[1].markets || [];
        function bySlug(slug) {
          /* Slug, never label. Polymarket renamed these outcomes from
             "Democratic Party" to "Bob Brooks (D)" on 10 Sep 2026 while the
             slugs held, and a label lookup found nothing at all. */
          return win.filter(function (m) { return (m.slug || "").indexOf(slug) >= 0; })[0];
        }
        var out = { at: new Date().toISOString(),
                    pm_dem: midOf(bySlug(cfg.slugs.D)),
                    pm_rep: midOf(bySlug(cfg.slugs.R)) };

        var active = mov.filter(live);
        out.brackets = active.length;
        var total = 0, weighted = 0;
        active.forEach(function (m) {
          var p = points[m.groupItemTitle];
          var q = midOf(m);
          if (p === undefined || q === null) return;
          total += q;
          weighted += q * p;
        });
        /* Normalised before weighting, exactly as the export does it: the raw
           mids on this ladder sum well above 1.00 because several brackets are
           quoted with very wide spreads. */
        out.margin = total > 0 ? weighted / total : null;
        return out;
      });
  }

  function paint(d) {
    render(d);
    var chart = (window.PA07.charts || {}).probability;
    if (chart && L.last && L.last.pm_dem !== null) {
      /* A separate marker past the end of the committed line, not an extra
         point appended to it. The line is what was collected; this is what the
         book says right now, and the two must stay visibly distinct. */
      chart.opts.markers = [{ date: today(), value: L.last.pm_dem,
                              color: C.D, label: "live" }];
      chart.redraw();
    }
    var chip = document.querySelector('#sources .src[data-id="polymarket"] .when');
    if (chip) chip.textContent = L.error ? "live poll failed" : "live, " + window.PA07.ago(L.last && L.last.at);
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
    /* A backgrounded tab should not keep hitting a public API. Re-poll when it
       comes back instead. */
    if (document.hidden) { schedule(d); return; }
    status("Polling...");
    L.tries += 1;
    pull(d).then(function (v) {
      L.last = v;
      L.error = null;
      paint(d);
      status("Updated " + new Date().toLocaleTimeString());
    }).catch(function (err) {
      L.error = String(err.message || err);
      paint(d);
      status("Last attempt failed.");
    }).then(function () { schedule(d); });
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
