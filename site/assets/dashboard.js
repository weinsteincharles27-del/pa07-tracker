/* The page, read top to bottom as one story: where the race stands, how it
   got there, where the two markets split, what the forecast and the polls
   say, and what margin the market expects. Every figure comes from
   site/data/*.json. The only arithmetic here is a subtraction against the
   price the lead is showing, so that "up 3 points in the past week" agrees
   with the number printed above it once live prices replace the build's.

   The three dated charts share one start date, so a spike in the first lines
   up with the same week in the other two. */
(function () {
  "use strict";

  var P = window.PA07, C = P.colours, elem = P.elem, fmt = window.Chart.fmt;
  var MINUS = "−", LETTERS = "ABCDEFGHIJ";

  function has(v) { return v !== null && v !== undefined; }
  function pct(v, dp) { return has(v) ? (v * 100).toFixed(dp === undefined ? 1 : dp) + "%" : "n/a"; }
  function size(v) { return Math.abs(v).toFixed(1); }
  function signed(v) { return (v > 0 ? "+" : v < 0 ? MINUS : "") + size(v); }
  function margin(v) { return has(v) ? (v > 0 ? "D+" : v < 0 ? "R+" : "") + Math.abs(v).toFixed(1) : "n/a"; }
  function day(iso) { return fmt.day(iso); }
  function short(iso) { return day(iso).replace(/ \d{4}$/, ""); }
  function since(points, from) { return (points || []).filter(function (p) { return p[0] >= from; }); }
  function text(host, s) { host.appendChild(document.createTextNode(s)); }

  /* Sections go into the page before they are drawn into, so each chart
     measures its real width on the first pass instead of redrawing. */
  function section(id, title) {
    var s = elem("section"), h = elem("h2", null, title);
    s.id = id; h.id = id + "-h";
    s.setAttribute("aria-labelledby", h.id);
    s.appendChild(h);
    document.getElementById("main").appendChild(s);
    return s;
  }

  function figure(host, legendItems, caption) {
    var fig = elem("figure", "chart"), plot = elem("div", "plot");
    if (legendItems) fig.appendChild(window.Chart.legend(legendItems));
    fig.appendChild(plot);
    if (caption) { var cap = elem("figcaption"); cap.innerHTML = caption; fig.appendChild(cap); }
    host.appendChild(fig);
    return plot;
  }

  /* A sourced event as a link, or plain text if it has no URL. */
  function link(e) {
    if (!e.url) return elem("span", null, e.text);
    var a = elem("a", null, e.text);
    a.href = e.url; a.target = "_blank"; a.rel = "noopener";
    return a;
  }

  function item(list, label, when, iso) {
    var li = elem("li"), t = elem("time", null, when), w = elem("span", "what");
    li.appendChild(elem("span", "pin", label));
    t.dateTime = iso;
    li.appendChild(t);
    li.appendChild(w);
    list.appendChild(li);
    return w;
  }

  /* The first day any of the dated charts has something to say: Polymarket's
     first quote or the first sourced event, whichever is earlier. Kalshi's
     history runs back to July 2025, but with nothing to compare it to. */
  function start(d) {
    var p = (d.series.series.pm_dem || [])[0], e = (d.divergence.events || [])[0];
    var a = p ? p[0] : null, b = e ? e.date : null;
    return a && b ? (a < b ? a : b) : a || b;
  }

  /* ------------------------------------------------------------- the lead */

  /* Freshest reading per venue wins. Polymarket's live read is always newer
     than the build. Kalshi's live file is written by a scheduled job that
     GitHub runs hours apart in practice, so it can be older than the build,
     and the timestamps decide. */
  function pick(snapV, snapAt, live) {
    if (live && has(live.v) && !(Date.parse(live.at) <= Date.parse(snapAt))) {
      return { v: live.v, at: live.at, live: true };
    }
    return { v: snapV, at: snapAt, live: false };
  }

  function story(avg, gap) {
    var c = (P.state.data.divergence.moves || {}).consensus || {}, out = [], last = 0;
    [[c.d7, "in the past week"], [c.d30, "over 30 days"],
     [c.since_primary, c.since_primary ? "since the " + short(c.since_primary.from) + " primary" : ""]]
      .forEach(function (x) {
        if (!x[0] || !has(x[0].start)) return;
        var v = (avg - x[0].start) * 100, dir = Math.abs(v) < 0.05 ? 0 : v > 0 ? 1 : -1;
        var clause = dir ? size(v) + " points " + x[1] : "unchanged " + x[1];
        out.push(!dir || dir === last ? clause : (dir > 0 ? "up " : "down ") + clause);
        last = dir;
      });
    var s = out.length < 2 ? out.join("") :
      out.slice(0, -1).join(", ") + " and " + out[out.length - 1];
    s = s ? s.charAt(0).toUpperCase() + s.slice(1) + ". " : "";
    var hi = gap > 0 ? "Polymarket" : "Kalshi", lo = gap > 0 ? "Kalshi" : "Polymarket";
    return s + (Math.abs(gap) < 0.0005 ? "The two markets agree." :
      hi + " is " + size(gap * 100) + " points higher than " + lo + ".");
  }

  function lead(live) {
    live = live || {};
    var d = P.state.data, s = d.headline.snapshot || {}, f = {};
    (d.manifest.freshness || []).forEach(function (x) { f[x.id] = x.snapshot_utc; });
    var pm = pick(s.pm_dem, f.polymarket, live.pm), k = pick(s.kalshi_dem, f.kalshi, live.k);
    var both = has(pm.v) && has(k.v), avg = both ? (pm.v + k.v) / 2 : has(pm.v) ? pm.v : k.v;

    var lede = document.getElementById("lede");
    lede.textContent = "";
    if (!has(avg)) {
      lede.textContent = "Neither market is quoting a price right now.";
    } else {
      text(lede, (both ? "The prediction markets put" : has(pm.v) ? "Polymarket puts" : "Kalshi puts") +
                 " Brooks’s chance of winning at ");
      lede.appendChild(elem("b", null, pct(avg)));
      text(lede, ".");
    }
    document.getElementById("since").textContent = both ? story(avg, pm.v - k.v) : "";

    var ul = document.getElementById("venues");
    ul.textContent = "";
    [["Polymarket", pm, false], ["Kalshi", k, true]].forEach(function (x) {
      var li = elem("li"), sw = elem("i", x[2] ? "dash" : null);
      sw.style.borderTopColor = C.D;
      li.appendChild(sw);
      li.appendChild(elem("span", null, x[0]));
      li.appendChild(elem("span", "v", has(x[1].v) ? pct(x[1].v) : "no quote"));
      li.appendChild(elem("span", "age", "updated " + P.ago(x[1].at)));
      ul.appendChild(li);
    });
    return { pm: pm, k: k };
  }

  function leadSection() {
    var s = elem("section", "lead");
    s.id = "lead";
    s.setAttribute("aria-label", "Where the race stands");
    ["lede", "since"].forEach(function (id) { var p = elem("p", id); p.id = id; s.appendChild(p); });
    var ul = elem("ul", "venues"), bar = elem("div", "livebar");
    ul.id = "venues"; bar.id = "livebar";
    s.appendChild(ul);
    s.appendChild(bar);
    document.getElementById("main").appendChild(s);
    lead();
  }

  /* ------------------------------------------ how the odds moved, and why */

  /* Every sourced event, plus the biggest one-day moves, as one dated list.
     A move and an event on the same day share a pin. */
  function moments(d) {
    var m = d.divergence.moves || {}, byDay = {}, big = [];
    function at(date) { return byDay[date] || (byDay[date] = { date: date, events: [], moves: [] }); }
    (d.divergence.events || []).forEach(function (e) { at(e.date).events.push(e); });
    ["polymarket", "kalshi"].forEach(function (v) {
      ((m[v] || {}).biggest_days || []).slice(0, 4).forEach(function (b) { big.push({ venue: v, b: b }); });
    });
    big.sort(function (x, y) { return Math.abs(y.b.pp) - Math.abs(x.b.pp); });
    big.slice(0, 6).forEach(function (x) { at(x.b.date).moves.push(x); });
    return Object.keys(byDay).sort().map(function (k, i) { byDay[k].n = String(i + 1); return byDay[k]; });
  }

  function odds(d, x0) {
    var S = d.series.series, dv = d.divergence.divergence || {}, list = moments(d);
    var sec = section("odds", "How the odds have moved");
    var plot = figure(sec, [
      { label: "Polymarket", color: C.D },
      { label: "Kalshi", color: C.D, dash: true }
    ], "Two real-money markets on the same question. Days when Kalshi’s bid and ask were more than " +
       Math.round((dv.wide_threshold || 0.25) * 100) + " cents apart are left out of its line. " +
       "Numbers mark the events and biggest one-day moves listed below.");
    var opts = {
      title: "Chance Brooks wins on Polymarket and Kalshi, with numbered events",
      series: [
        { label: "Polymarket", points: since(S.pm_dem, x0), color: C.D, width: 2.2 },
        { label: "Kalshi", points: since(S.k_dem_tight, x0), color: C.D, width: 2, dash: "5 4" }
      ],
      moments: list.map(function (o) { return { date: o.date, label: o.n }; }),
      refLines: [{ y: 0.5, label: "50%" }],
      xMin: x0, yMin: 0.3, yMax: 0.9, yFormat: pct
    };
    P.charts = P.charts || {};
    P.charts.probability = { opts: opts, redraw: window.Chart.line(plot, opts) };

    var ol = elem("ol", "moments split");
    list.forEach(function (o) {
      var w = item(ol, o.n, day(o.date), o.date);
      o.events.forEach(function (e) {
        if (w.childNodes.length) text(w, " ");
        w.appendChild(link(e));
        text(w, ".");
      });
      o.moves.forEach(function (x) {
        var b = x.b;
        text(w, (w.childNodes.length ? " " : "") + (x.venue === "kalshi" ? "Kalshi" : "Polymarket") +
                (b.pp < 0 ? " fell " : " rose ") + size(b.pp) + " points" +
                (o.events.length ? " that day" : " in a day") + ", " + pct(b.from) + " to " + pct(b.to) + ".");
      });
    });
    sec.appendChild(ol);
  }

  /* ------------------------------------------------ where the venues split */

  function divergence(d, x0) {
    var S = d.series.series, dv = d.divergence.divergence || {};
    var eps = (dv.episodes || []).slice().sort(function (a, b) { return a.from < b.from ? -1 : 1; });
    var sec = section("divergence", "Where the two markets disagreed");
    var plot = figure(sec, [{ label: "Polymarket minus Kalshi", color: C.GAP }],
      "Above zero, Polymarket gave Brooks the better odds; below zero, Kalshi did. " +
      "Over " + dv.days_tight + " days the gap averaged " + dv.mean_abs_pp + " points." +
      (eps.length ? " Shaded: the longest disagreements." : ""));
    window.Chart.line(plot, {
      title: "Polymarket minus Kalshi, Democratic win probability",
      series: [{ label: "Gap", points: since(S.divergence, x0), color: C.GAP, width: 2 }],
      moments: eps.map(function (e, i) { return { date: e.from, to: e.to, label: LETTERS[i] }; }),
      refLines: [{ y: 0 }],
      xMin: x0, yMin: -0.4, yMax: 0.4,
      yFormat: function (v) { return signed(v * 100).replace(".0", ""); },
      tipFormat: function (v) { return signed(v * 100) + " points"; }
    });

    if (!eps.length) return;
    var ol = elem("ol", "moments");
    eps.forEach(function (e, i) {
      var w = item(ol, LETTERS[i], day(e.from), e.from);
      text(w, e.days + " days, through " + day(e.to) + ". " +
              (e.direction === "kalshi_higher" ? "Kalshi" : "Polymarket") +
              " was higher by up to " + size(e.peak_pp) + " points. ");
      if (e.note) text(w, e.note);
      else w.appendChild(elem("span", "muted", "Not yet annotated."));
      (e.events || []).forEach(function (x) { text(w, " "); w.appendChild(link(x)); });
    });
    sec.appendChild(ol);
  }

  /* ------------------------------------------- the forecast and the polls */

  function forecast(d, x0) {
    var S = d.series.series, m = d.polls.model || {}, s = d.headline.snapshot || {};
    var polls = d.polls.polls || [];
    var sec = section("forecast", "The markets against the forecast and the polls");
    var gap = has(s.pm_dem) && has(m.dem_win_prob) ? (s.pm_dem - m.dem_win_prob) * 100 : null;

    var plot = figure(sec, [
      { label: "Polymarket", color: C.D },
      { label: "PollsMax model", color: C.MODEL }
    ], "The PollsMax forecast" + (m.retrieved_utc ? ", last read " + day(m.retrieved_utc.slice(0, 10)) + "," : "") +
       " puts Brooks at " + pct(m.dem_win_prob) +
       (gap !== null ? "; Polymarket is " + Math.abs(gap).toFixed(0) + " points " + (gap >= 0 ? "higher" : "lower") : "") + ".");
    window.Chart.line(plot, {
      title: "Polymarket against the PollsMax model",
      series: [
        { label: "Polymarket", points: since(S.pm_dem, x0), color: C.D, width: 2.2 },
        { label: "Model", points: since(S.model_dem, x0), color: C.MODEL, width: 2.2 }
      ],
      refLines: [{ y: 0.5, label: "50%" }],
      xMin: x0, yMin: 0.3, yMax: 0.9, yFormat: pct
    });

    var prose = elem("div", "prose");
    prose.style.marginTop = "1.25rem";
    if (polls.length) {
      /* polls.json is sorted oldest first, so the latest poll is the last row. */
      var p = polls[polls.length - 1];
      prose.appendChild(elem("p", null,
        (polls.length === 1 ? "There has been one public poll so far: " :
          "There have been " + polls.length + " public polls. The latest is ") +
        p.pollster + " for " + (p.sponsor || "an undisclosed sponsor") + ", " + day(p.end) +
        ", with Brooks at " + p.dem.toFixed(0) + "% to Mackenzie’s " + p.rep.toFixed(0) + "%." +
        (p.partisan === "D" ? " It was Democratic-sponsored." : p.partisan === "R" ? " It was Republican-sponsored." : "")));
    }
    prose.appendChild(elem("p", null,
      "Both have missed in this district before. In the primary, every public poll understated " +
      "Brooks: the last had him at 26%, and he took 41.4%. In 2024, Polymarket had Susan Wild at " +
      "68.5% on election morning, and she lost by a point."));
    sec.appendChild(prose);
  }

  /* ------------------------------------------------------------ the margin */

  function marginSection(d) {
    var pmm = (d.distribution || {}).polymarket_margin || {}, s = d.headline.snapshot || {};
    var sec = section("margin", "How wide a margin Polymarket expects");
    var bars = (pmm.brackets || []).map(function (b) {
      return { label: b.bracket.replace("Republican ", "R ").replace("Democrat ", "D "),
               value: b.normalised, color: b.points < 0 ? C.R : C.D };
    });
    var plot = figure(sec, null, "Polymarket’s expected margin is <span class=\"num\" id=\"margin-now\">" +
      margin(s.expected_margin_pts) + "</span> points<span id=\"margin-when\"> at the last build</span>. " +
      "Each bar is the chance the final margin lands in that range.");
    window.Chart.bars(plot, { title: "Margin of victory, implied probability", bars: bars,
                              yFormat: function (v) { return (v * 100).toFixed(0) + "%"; } });
  }

  /* ------------------------------------------------------------ downloads */

  function downloads(d) {
    var w = d.manifest.workbook || {}, p = document.getElementById("downloads");
    if (!p) return;
    text(p, "Download ");
    if (w.available) {
      var a = elem("a", null, "the Excel workbook");
      a.href = w.href; a.setAttribute("download", "");
      p.appendChild(a);
      text(p, (w.bytes ? " (" + Math.round(w.bytes / 1024) + " KB)" : "") + " or ");
    }
    var j = elem("a", null, "the daily series as JSON");
    j.href = "data/series-full.json";
    p.appendChild(j);
    text(p, ".");
  }

  /* --------------------------------------------------------------- mount */

  document.addEventListener("data:ready", function (ev) {
    var d = ev.detail, x0 = start(d);
    [leadSection, odds, divergence, forecast, marginSection, downloads].forEach(function (fn) {
      try { fn(d, x0); }
      catch (e) { console.error(fn.name, e); }
    });
    P.lead = lead;
    /* live.js fills the live bar and starts polling on this. */
    document.dispatchEvent(new CustomEvent("dashboard:ready", { detail: d }));
  });
})();
