/* The page. Every section reads from site/data/*.json; nothing is recomputed
   here that the export did not already compute. Kept deliberately short: one
   sentence under each chart, and the numbers do the talking. */
(function () {
  "use strict";

  var C = window.PA07.colours, elem = window.PA07.elem;

  function pct(v, dp) { return v === null || v === undefined ? "n/a" : (v * 100).toFixed(dp === undefined ? 1 : dp) + "%"; }
  function pp(v, dp) { return v === null || v === undefined ? "n/a" : (v > 0 ? "+" : "") + v.toFixed(dp === undefined ? 1 : dp) + " pp"; }
  function margin(v) { return v === null || v === undefined ? "n/a" : (v > 0 ? "D+" : v < 0 ? "R+" : "") + Math.abs(v).toFixed(1); }
  function day(iso) { return window.Chart.fmt.day(iso); }

  function block(id, title, blurb) {
    var s = elem("section", "block"); s.id = id;
    var h = elem("header");
    h.appendChild(elem("h2", null, title));
    if (blurb) h.appendChild(elem("p", null, blurb));
    s.appendChild(h);
    return s;
  }

  function chart(host, legendItems, caption) {
    if (legendItems) host.appendChild(window.Chart.legend(legendItems));
    var fig = elem("figure", "chart"), plot = elem("div", "plot");
    fig.appendChild(plot);
    if (caption) { var cap = elem("figcaption"); cap.innerHTML = caption; fig.appendChild(cap); }
    host.appendChild(fig);
    return plot;
  }

  function tile(k, v, sub, cls) {
    var li = elem("li", "stat" + (cls ? " " + cls : ""));
    li.appendChild(elem("div", "k", k));
    li.appendChild(elem("div", "v num", v));
    if (sub) li.appendChild(elem("div", "sub", sub));
    return li;
  }

  function table(host, head, rows) {
    var t = elem("table", "tbl"), tr = elem("tr");
    head.forEach(function (h) { tr.appendChild(elem("th", null, h)); });
    t.appendChild(tr);
    rows.forEach(function (r) {
      var row = elem("tr");
      r.forEach(function (c, i) {
        var td = elem("td", i ? "num" : null);
        if (c && c.nodeType) td.appendChild(c); else td.textContent = c;
        row.appendChild(td);
      });
      t.appendChild(row);
    });
    host.appendChild(t);
    return t;
  }

  /* A sourced event as a link, or plain text if it has no URL. */
  function eventLink(e) {
    if (!e) return "";
    if (!e.url) return elem("span", null, e.text);
    var a = elem("a", null, e.text);
    a.href = e.url; a.target = "_blank"; a.rel = "noopener";
    return a;
  }

  function signed(v) {
    var s = elem("span", v > 0 ? "up" : v < 0 ? "down" : null, pp(v));
    return s;
  }

  /* ------------------------------------------------------------ 1. headline */

  function headline(d) {
    var s = d.headline.snapshot || {}, m = d.divergence.moves || {}, c = m.consensus || {};
    var sec = block("headline", "Where the race stands");
    var ul = elem("ul", "stats");
    ul.appendChild(tile("Brooks wins", pct(s.consensus_dem),
      "Polymarket " + pct(s.pm_dem) + " · Kalshi " + pct(s.kalshi_dem), "lead"));
    ul.appendChild(tile("Past 7 days", c.d7 ? pp(c.d7.pp) : "n/a",
      c.d7 ? "from " + pct(c.d7.start) : "", c.d7 && c.d7.pp < 0 ? "down" : c.d7 && c.d7.pp > 0 ? "up" : ""));
    ul.appendChild(tile("Past 30 days", c.d30 ? pp(c.d30.pp) : "n/a",
      c.d30 ? "from " + pct(c.d30.start) : "", c.d30 && c.d30.pp < 0 ? "down" : c.d30 && c.d30.pp > 0 ? "up" : ""));
    ul.appendChild(tile("Since the primary", c.since_primary ? pp(c.since_primary.pp) : "n/a",
      "19 May 2026", c.since_primary && c.since_primary.pp > 0 ? "up" : "down"));
    ul.appendChild(tile("Gap between markets", pp(s.divergence !== null && s.divergence !== undefined ? s.divergence * 100 : null),
      "Polymarket minus Kalshi"));
    sec.appendChild(ul);
    var live = elem("p", "fine", "The headline is the average of the two markets. Live prices are below.");
    sec.appendChild(live);
    return sec;
  }

  /* --------------------------------------------------- 2. the headline chart */

  function probability(d) {
    var S = d.series.series;
    var sec = block("probability", "Chance Brooks wins");
    var plot = chart(sec, [
      { label: "Polymarket", color: C.D },
      { label: "Kalshi", color: C.D, dash: true }
    ], "Two real-money markets on the same question. Days when Kalshi's bid and ask were more than 25 cents apart are left out of its line.");
    var opts = {
      title: "Democratic win probability on Polymarket and Kalshi",
      series: [
        { label: "Polymarket", points: S.pm_dem, color: C.D, width: 2.2 },
        { label: "Kalshi", points: S.k_dem_tight, color: C.D, width: 2, dash: "5 4" }
      ],
      refLines: [{ y: 0.5, label: "50%" }],
      yMin: 0.3, yMax: 0.9, yFormat: pct
    };
    window.PA07.charts = window.PA07.charts || {};
    window.PA07.charts.probability = { opts: opts, redraw: window.Chart.line(plot, opts) };
    return sec;
  }

  /* --------------------------------------------------------- 3. the moves */

  function moves(d) {
    var m = d.divergence.moves || {};
    var sec = block("moves", "Biggest one-day moves");
    var rows = [];
    ["polymarket", "kalshi"].forEach(function (v) {
      ((m[v] || {}).biggest_days || []).slice(0, 4).forEach(function (b) {
        rows.push([v === "polymarket" ? "Polymarket" : "Kalshi", day(b.date),
                   signed(b.pp), pct(b.from) + " → " + pct(b.to),
                   eventLink((b.events || [])[0])]);
      });
    });
    rows.sort(function (a, b) { return Math.abs(parseFloat(b[2].textContent)) - Math.abs(parseFloat(a[2].textContent)); });
    table(sec, ["Venue", "Day", "Move", "From → to", "Same day"], rows.slice(0, 6));
    return sec;
  }

  /* --------------------------------------------- 4. where the venues split */

  function divergence(d) {
    var S = d.series.series, dv = d.divergence.divergence || {};
    var sec = block("divergence", "Where Polymarket and Kalshi disagreed");
    var plot = chart(sec, [{ label: "Polymarket minus Kalshi", color: "#6B7C93" }],
      "Above zero, Polymarket gave Brooks the better odds; below zero, Kalshi did. " +
      "Over " + dv.days_tight + " days the gap averaged " + dv.mean_abs_pp + " points.");
    window.Chart.line(plot, {
      title: "Polymarket minus Kalshi, Democratic win probability",
      series: [{ label: "Divergence", points: S.divergence, color: "#6B7C93", width: 2 }],
      refLines: [{ y: 0, label: "0" }],
      yMin: -0.4, yMax: 0.4, yFormat: function (v) { return (v * 100).toFixed(0) + " pp"; }
    });

    var eps = dv.episodes || [];
    if (eps.length) {
      var h = elem("h3", null, "Longest disagreements");
      sec.appendChild(h);
      table(sec, ["Period", "Length", "Peak gap", "Higher on Brooks", "What was happening"],
        eps.map(function (e) {
          var who = e.direction === "kalshi_higher" ? "Kalshi" : "Polymarket";
          var cell = elem("span", e.note ? null : "muted", e.note || "not yet annotated");
          (e.events || []).forEach(function (x) {
            cell.appendChild(document.createTextNode(" "));
            var a = eventLink(x);
            a.className = "fine";
            cell.appendChild(a);
          });
          return [day(e.from) + " to " + day(e.to), e.days + " days",
                  signed(e.peak_pp), who, cell];
        }));
    }

    return sec;
  }

  /* ------------------------------------ 6. do the markets know anything? */

  function validation(d) {
    var S = d.series.series, m = d.polls.model || {}, s = d.headline.snapshot || {};
    var polls = d.polls.polls || [];
    var sec = block("validation", "Markets against the forecast and the polls");
    var gap = (s.consensus_dem && m.dem_win_prob) ? (s.consensus_dem - m.dem_win_prob) * 100 : null;

    var plot = chart(sec, [
      { label: "Polymarket", color: C.D },
      { label: "PollsMax model", color: C.MODEL }
    ], "The PollsMax forecast puts Brooks at " + pct(m.dem_win_prob) +
       "; the markets are " + (gap !== null ? Math.abs(gap).toFixed(0) + " points " + (gap >= 0 ? "higher" : "lower") : "n/a") + ".");
    window.Chart.line(plot, {
      title: "Polymarket against the PollsMax model",
      series: [
        { label: "Polymarket", points: S.pm_dem, color: C.D, width: 2.2 },
        { label: "Model", points: S.model_dem, color: C.MODEL, width: 2.2 }
      ],
      refLines: [{ y: 0.5, label: "50%" }],
      yMin: 0.3, yMax: 0.9, yFormat: pct
    });

    var ul = elem("ul", "plain");
    if (polls.length) {
      var p0 = polls[0];
      ul.appendChild(elem("li", null, "Polls: " + (polls.length === 1 ? "one public poll so far" : polls.length + " public polls") +
        ", " + p0.pollster + " for " + (p0.sponsor || "an undisclosed sponsor") + ", " + day(p0.end) +
        ", Brooks " + p0.dem.toFixed(0) + "% to " + p0.rep.toFixed(0) + "%." +
        (p0.partisan === "D" ? " Democratic-sponsored." : "")));
    }
    ul.appendChild(elem("li", null, "Primary: every public poll understated Brooks. The last had him at 26%; he took 41.4%."));
    ul.appendChild(elem("li", null, "2024: Polymarket had Susan Wild at 68.5% on election morning. She lost by a point."));
    sec.appendChild(ul);
    return sec;
  }

  /* ------------------------------------------------------ 7. the margin */

  function distribution(d) {
    var dist = d.distribution || {}, pmm = dist.polymarket_margin || {}, s = d.headline.snapshot || {};
    var sec = block("margin", "Expected margin of victory");
    var bars = (pmm.brackets || []).map(function (b) {
      return { label: b.bracket.replace("Republican ", "R ").replace("Democrat ", "D "),
               value: b.normalised, color: b.points < 0 ? C.R : C.D };
    });
    var plot = chart(sec, null, "Polymarket's expected margin is " + margin(s.expected_margin_pts) +
      " points. Each bar is the chance the final margin lands in that range.");
    window.Chart.bars(plot, { title: "Margin of victory, implied probability", bars: bars,
                              yFormat: function (v) { return (v * 100).toFixed(0) + "%"; } });
    return sec;
  }

  /* -------------------------------------------------------- 8. download */

  function download(d) {
    var w = d.manifest.workbook || {};
    var sec = block("download", "Download");
    var ul = elem("ul", "plain");
    if (w.available) {
      var a = elem("a", null, "Excel workbook");
      a.href = w.href; a.setAttribute("download", "");
      var li = elem("li"); li.appendChild(a);
      li.appendChild(document.createTextNode(" · 13 sheets" +
        (w.bytes ? ", " + Math.round(w.bytes / 1024) + " KB" : "")));
      ul.appendChild(li);
    }
    var j = elem("a", null, "Daily series as JSON");
    j.href = "data/series-full.json";
    var lj = elem("li"); lj.appendChild(j);
    lj.appendChild(document.createTextNode(" · daily prices, both markets"));
    ul.appendChild(lj);
    sec.appendChild(ul);
    return sec;
  }

  /* --------------------------------------------------------------- mount */

  document.addEventListener("data:ready", function (ev) {
    var d = ev.detail, main = document.getElementById("main");
    [headline, probability, moves, divergence, validation, distribution, download]
      .forEach(function (fn) {
        try { main.appendChild(fn(d)); }
        catch (e) { console.error(fn.name, e); }
      });
    /* live.js mounts its panel and starts polling on this. */
    document.dispatchEvent(new CustomEvent("dashboard:ready", { detail: d }));
  });
})();
