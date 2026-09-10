/* The exhibits.
 *
 * Four charts carry the argument, in this order:
 *
 *   1. Democratic win probability on both venues, with the 50% line. The
 *      headline: this race is priced as a Democratic favourite, not a tossup.
 *   2. The same market against PollsMax's model on the same date axis. That
 *      gap is the most interesting number anywhere in this project: the
 *      market and the model disagree by about twenty points about the same
 *      race, and neither of them is obviously wrong.
 *   3. Where the market thinks the margin lands.
 *   4. What the markets say about the margin against what the polling says,
 *      which is one poll.
 *
 * Everything else is secondary and folded away. A page that shows thirteen
 * charts is a page where the reader picks one at random.
 */
(function () {
  "use strict";

  var C = window.PA07.colours, F = window.Chart.fmt, elem = window.PA07.elem;

  function pct(v, dp) { return v === null || v === undefined ? "n/a" : (v * 100).toFixed(dp === undefined ? 1 : dp) + "%"; }
  function margin(v, dp) {
    if (v === null || v === undefined) return "n/a";
    dp = dp === undefined ? 1 : dp;
    return (v > 0 ? "D+" : v < 0 ? "R+" : "") + Math.abs(v).toFixed(dp);
  }

  function block(id, title, blurb) {
    var s = elem("section", "block");
    s.id = id;
    var h = elem("header");
    h.appendChild(elem("h2", null, title));
    if (blurb) h.appendChild(elem("p", null, blurb));
    s.appendChild(h);
    return s;
  }

  function chart(host, legendItems, caption) {
    if (legendItems) host.appendChild(window.Chart.legend(legendItems));
    var fig = elem("figure", "chart");
    var plot = elem("div", "plot");
    fig.appendChild(plot);
    if (caption) {
      var cap = elem("figcaption");
      cap.innerHTML = caption;
      fig.appendChild(cap);
    }
    host.appendChild(fig);
    return plot;
  }

  function note(host, html, kind) {
    var n = elem("div", kind || "note");
    n.innerHTML = html;
    host.appendChild(n);
    return n;
  }

  /* ------------------------------------------------------------ stat tiles */

  function tile(k, v, sub, cls) {
    var li = elem("li", "stat" + (cls ? " " + cls : ""));
    li.appendChild(elem("div", "k", k));
    li.appendChild(elem("div", "v num", v));
    if (sub) li.appendChild(elem("div", "sub", sub));
    return li;
  }

  function headline(d) {
    var s = d.headline.snapshot || {};
    var poll = d.polls.average || {};
    var model = d.polls.model || {};
    var sec = block("headline", "Where the race stands",
      "Figures as of the last scheduled build. Every one of them is derived from the " +
      "collected market data, not from the workbook.");
    var ul = elem("ul", "stats");

    var gap = (s.consensus_dem !== null && s.consensus_dem !== undefined &&
               model.dem_win_prob !== null && model.dem_win_prob !== undefined)
      ? (s.consensus_dem - model.dem_win_prob) * 100 : null;

    ul.appendChild(tile("Consensus P(Brooks wins)", pct(s.consensus_dem),
      "Polymarket " + pct(s.pm_dem) + " · Kalshi " + pct(s.kalshi_dem), "lead"));
    ul.appendChild(tile("Market minus model",
      gap === null ? "n/a" : (gap > 0 ? "+" : "") + gap.toFixed(1) + " pts",
      "Model " + pct(model.dem_win_prob) + " (PollsMax, " +
      window.PA07.ago(model.retrieved_utc) + ")"));
    ul.appendChild(tile("Market-implied margin", margin(s.expected_margin_pts, 1),
      "Polymarket ladder, normalised"));
    ul.appendChild(tile("Polling average", margin(poll.margin, 1),
      d.polls.polls.length + " general poll" + (d.polls.polls.length === 1 ? "" : "s") +
      " · " + margin(poll.adjusted_margin, 1) + " after the partisan haircut"));
    ul.appendChild(tile("Cross-venue divergence",
      s.divergence === null || s.divergence === undefined ? "n/a"
        : ((s.divergence >= 0 ? "+" : "") + (s.divergence * 100).toFixed(1) + " pp"),
      "Polymarket minus Kalshi"));
    ul.appendChild(tile("Expected turnout", F.thousands(s.expected_turnout),
      "Kalshi ladder · 403,314 in 2024"));
    ul.appendChild(tile("Expected PA Democratic seats",
      s.expected_dem_seats === null || s.expected_dem_seats === undefined ? "n/a"
        : s.expected_dem_seats.toFixed(1),
      "of 17 · baseline 8 today"));
    ul.appendChild(tile("Days to the election",
      String(d.manifest.race.days_to_election), "3 November 2026"));
    sec.appendChild(ul);
    return sec;
  }

  /* ------------------------------------------------- 1. the headline chart */

  function probability(d) {
    var S = d.series.series;
    var sec = block("probability", "Democratic win probability, both venues",
      "The one chart to read. Two independent books, priced in real money, on the same " +
      "question. Anything above the 50% line is a Democratic favourite.");
    var wide = S.k_dem_wide || [];
    var plot = chart(sec, [
      { label: "Polymarket (last trade)", color: C.D },
      { label: "Kalshi (bid/ask mid)", color: C.D, dash: true },
      { label: "Kalshi, book one-sided", color: C.D, dot: true }
    ], "The two series are not the same measurement, and on books this thin that matters. " +
       "Polymarket's daily history is its last traded price; Kalshi's is the midpoint of its " +
       "closing bid and ask. Breaks in a line are days the venue did not quote, and nothing is " +
       "interpolated across them. The " + wide.length + " hollow point" +
       (wide.length === 1 ? " is a day" : "s are days") + " when Kalshi's closing book was " +
       "wider than 25 cents bid to ask. The midpoint of a one-cent bid against an 84-cent " +
       "ask is arithmetic, not a price, so it is shown but not joined into the line.");

    window.Chart.line(plot, {
      title: "Democratic win probability on Polymarket and Kalshi",
      series: [
        { label: "Polymarket", points: S.pm_dem, color: C.D, width: 2.2 },
        { label: "Kalshi", points: S.k_dem_tight, color: C.D, width: 2, dash: "5 4" },
        { label: "Kalshi (one-sided book)", points: wide, color: C.D, dots: true, endDot: false }
      ],
      refLines: [{ y: 0.5, label: "50%" }],
      yMin: 0.3, yMax: 0.9,
      yFormat: pct
    });
    return sec;
  }

  /* -------------------------------------------------- 2. model vs market */

  function modelVsMarket(d) {
    var S = d.series.series;
    var m = d.polls.model || {};
    var s = d.headline.snapshot || {};
    var gap = (s.consensus_dem && m.dem_win_prob)
      ? ((s.consensus_dem - m.dem_win_prob) * 100).toFixed(1) : null;

    var sec = block("model", "The market against the model",
      "PollsMax runs a statistical forecast off polling, Trump approval, the generic ballot, " +
      "past results, incumbency and partisan lean. The market runs off money. They disagree " +
      (gap ? "by about " + gap + " points" : "") + " about the same race.");

    var plot = chart(sec, [
      { label: "Polymarket", color: C.D },
      { label: "PollsMax model", color: C.MODEL },
      { label: "Model simulation band", color: C.MODEL, dot: true }
    ], "The model line stops where PollsMax's own published series stops. It is a hand-curated " +
       "extraction, not a feed this project polls, so the two lines are not equally fresh and " +
       "the chart shows that rather than extending the model to today.");

    window.Chart.line(plot, {
      title: "Polymarket against the PollsMax model",
      series: [
        { label: "Polymarket", points: S.pm_dem, color: C.D, width: 2.2 },
        { label: "Model", points: S.model_dem, color: C.MODEL, width: 2.2 }
      ],
      bands: [{ upper: S.model_dem_upper, lower: S.model_dem_lower, color: C.MODEL }],
      refLines: [{ y: 0.5, label: "50%" }],
      yMin: 0.3, yMax: 0.9,
      yFormat: pct
    });

    var vol = (d.caveats.caveats.filter(function (c) { return c.id === "equal-weight"; })[0]
               || {}).figures;
    note(sec,
      "<b>Neither number is obviously the right one.</b><p>The model is anchored on one " +
      "Democratic-sponsored poll and on fundamentals that lean Republican in this district " +
      "(past results and incumbency carry more weight in PollsMax's own diagram for PA-7 " +
      "than the generic ballot does). The market is real money, but only about " +
      (vol && vol.pm_volume ? "$" + F.thousands(vol.pm_volume) : "$30,000") +
      " of it has ever changed hands on the winner event. " + (gap || "Twenty") +
      " points of disagreement between a thin market and a lightly-fed model is an open " +
      "question, not an arbitrage.</p>",
      "note");
    return sec;
  }

  /* ------------------------------------------- 3. margin-of-victory shape */

  function distribution(d) {
    var pm = d.distribution.polymarket_margin;
    var ka = d.distribution.kalshi_margin;
    var sec = block("distribution", "Where the margin lands",
      "Polymarket sells ten mutually exclusive brackets that sum to one race. This is the " +
      "market's whole distribution, not just its centre.");

    var bars = pm.brackets.map(function (b) {
      return {
        label: b.bracket, short: b.bracket.replace("Democrat ", "D ").replace("Republican ", "R "),
        value: b.normalised, color: b.points > 0 ? C.D : C.R,
        note: "raw mid " + pct(b.mid) + " · bid " + pct(b.bid) + " / ask " + pct(b.ask) +
              " · spread " + (b.spread * 100).toFixed(1) + " pts"
      };
    });
    /* The zero line goes between the last Republican bracket and the first
       Democratic one, so the chart reads as one signed axis. */
    var zeroAt = pm.brackets.findIndex(function (b) { return b.points > 0; });

    var plot = chart(sec, [
      { label: "Democratic margin", color: C.D, dot: true },
      { label: "Republican margin", color: C.R, dot: true }
    ], "Normalised so the ten brackets sum to 100%. The raw mids sum to " +
       pct(pm.raw_total) + " because several thin brackets are quoted with very wide spreads, " +
       "and a wide spread inflates its own midpoint. Hover a bar for its raw quote.");

    window.Chart.bars(plot, {
      title: "Polymarket margin-of-victory distribution",
      bars: bars, zeroAt: zeroAt, yFormat: pct
    });

    /* Kalshi's version of the same question, which is where the arithmetic
       gets interesting and where the workbook's most buried caveat lives. */
    var sub = elem("div");
    sub.appendChild(elem("h3", null, "The same question on Kalshi, differenced into buckets"));
    var kbars = ka.buckets.map(function (b) {
      return {
        label: (b.side === "D" ? "Democrats " : "Republicans ") + b.label,
        short: b.side + " " + b.label.replace(" pts", ""),
        value: b.prob, color: b.side === "D" ? C.D : C.R,
        note: b.derived ? "derived from the winner market" + (b.raw !== null && b.raw < 0
              ? " · raw " + pct(b.raw) + ", clamped to zero" : "")
          : (b.prob === null ? "no two-sided quote on one of the rungs" : "")
      };
    });
    var kplot = chart(sub, null,
      "Kalshi sells nested thresholds, P(margin ≥ 3) and P(margin ≥ 6), so buckets come " +
      "from differencing adjacent strikes. Bars marked <b>n/q</b> are brackets where a rung " +
      "has no two-sided quote; they are not zero, and showing them as zero would assert the " +
      "market had ruled that outcome out.");
    window.Chart.bars(kplot, { title: "Kalshi margin buckets", bars: kbars, yFormat: pct });
    sec.appendChild(sub);

    var disc = ka.clamp_discarded || {};
    var bad = Object.keys(disc).filter(function (k) { return disc[k] < 0; });
    note(sec,
      "<b>The 0-3 buckets are a subtraction across two separate markets.</b>" +
      "<p>Kalshi quotes no 0-3 rung, so each side's tossup bucket is P(wins) from the winner " +
      "market minus P(wins by 3+) from the margin ladder. Two independently quoted markets " +
      "can disagree into a negative probability. Negatives are clamped at zero so the chart " +
      "stays readable, and the clamped amount is reported here, because on the workbook it " +
      "appears only inside a consistency check, which is exactly where nobody looks.</p>" +
      "<p class='num'>" + (bad.length
        ? bad.map(function (k) {
            return (k === "D" ? "Democratic" : "Republican") + " side: " + pct(disc[k]) +
                   " of probability discarded by the clamp.";
          }).join("<br>")
        : "Right now the clamp is discarding nothing" +
          (ka.unquoted ? ", though " + ka.unquoted + " of these buckets have no two-sided quote to check."
                       : ".")) + "</p>",
      "caveat medium");
    return sec;
  }

  /* ------------------------------------------------- 4. markets vs polls */

  function marketsVsPolls(d) {
    var S = d.series.series;
    var P = d.polls;
    var sec = block("margin", "Markets against polls, on margin",
      "Probability of winning and expected size of the win are different questions, and the " +
      "polling only answers the second one. This is every source that has an opinion about " +
      "the margin, on one axis.");

    var markers = P.polls.filter(function (p) { return p.margin !== null && p.end; })
      .map(function (p) {
        return { date: p.end, value: p.margin, color: C.POLL,
                 label: p.pollster + " " + margin(p.margin, 0) };
      });

    var plot = chart(sec, [
      { label: "Polymarket ladder", color: C.D },
      { label: "Kalshi ladder", color: C.D, dash: true },
      { label: "PollsMax projected margin", color: C.MODEL },
      { label: "Public poll", color: C.POLL, dot: true }
    ], "Positive is a Democratic margin. The market lines are the probability-weighted " +
       "expected margin across each venue's brackets, normalised. The poll is a single " +
       "field-period result placed at its end date, not a line. One point is not a trend.");

    window.Chart.line(plot, {
      title: "Expected margin from the markets, the model and the polls",
      series: [
        { label: "Polymarket", points: S.pm_margin, color: C.D, width: 2.2 },
        { label: "Kalshi", points: S.k_margin, color: C.D, width: 2, dash: "5 4" },
        { label: "Model", points: S.model_margin, color: C.MODEL, width: 2.2 }
      ],
      markers: markers,
      refLines: [{ y: 0, label: "tied" }],
      yFormat: function (v) { return margin(v, 0); },
      tipFormat: function (v) { return margin(v, 2); }
    });

    var avg = P.average || {};
    note(sec,
      "<b>The polling average is one poll.</b>" +
      "<p>" + (P.polls.length === 1 ? "Exactly one" : String(P.polls.length)) +
      " public general-election poll exists for this race" +
      (P.polls[0] ? ": " + P.polls[0].pollster +
        (P.polls[0].sponsor ? " for " + P.polls[0].sponsor : "") +
        ", " + P.polls[0].start + " to " + P.polls[0].end +
        ", n=" + P.polls[0].n + (P.polls[0].assumed_n ? " (assumed)" : "") : "") +
      ", and it is Democratic-sponsored. The average is a single data point wearing a " +
      "weighting scheme: recency weight, sample-size weight and a partisan haircut all apply, " +
      "and none of them add information the one poll does not have. " +
      margin(avg.margin, 1) + " unadjusted, " + margin(avg.adjusted_margin, 1) +
      " after the haircut.</p>",
      "caveat high");
    return sec;
  }

  /* ------------------------------------------------------------ secondary */

  function secondary(d) {
    var S = d.series.series, dist = d.distribution;
    var sec = block("secondary", "The rest of it",
      "Useful, but not the argument. Open what you want.");

    function fold(title, build) {
      var det = elem("details");
      det.appendChild(elem("summary", null, title));
      var body = elem("div");
      det.appendChild(body);
      /* Charts measure their container, and a closed <details> has width 0.
         Building on first open is both cheaper and the only way the widths
         come out right. */
      var built = false;
      det.addEventListener("toggle", function () {
        if (det.open && !built) { built = true; build(body); }
      });
      sec.appendChild(det);
    }

    fold("Cross-venue divergence", function (body) {
      var plot = chart(body, [{ label: "Polymarket minus Kalshi", color: C.D }],
        "Zero means the two books agree. Sustained divergence on a pair this thin is usually " +
        "one venue's book going stale, not a trade.");
      window.Chart.line(plot, {
        series: [{ label: "Divergence", points: S.divergence, color: C.D, width: 2 }],
        refLines: [{ y: 0, label: "agreement" }],
        yFormat: function (v) { return (v * 100).toFixed(0) + " pp"; },
        tipFormat: function (v) { return (v * 100).toFixed(1) + " pp"; },
        height: 200
      });
    });

    fold("Kalshi bid/ask spread on the Democratic contract", function (body) {
      var plot = chart(body, [
        { label: "YES bid", color: C.D },
        { label: "YES ask", color: C.D, dash: true }
      ], "The YES ask is derived as 1 minus the best NO bid. Kalshi's market object returns " +
         "null for yes_ask on these contracts, so top of book comes from the order book. A " +
         "widening band is liquidity leaving, and it moves the midpoint without anyone " +
         "changing their mind.");
      window.Chart.line(plot, {
        series: [
          { label: "Bid", points: S.k_dem_bid, color: C.D, width: 1.8 },
          { label: "Ask", points: S.k_dem_ask, color: C.D, width: 1.8, dash: "4 3" }
        ],
        bands: [{ upper: S.k_dem_ask, lower: S.k_dem_bid, color: C.D, opacity: 0.10 }],
        yFormat: pct, height: 200
      });
    });

    fold("Kalshi open interest", function (body) {
      var plot = chart(body, [{ label: "Open interest", color: C.D }],
        "The larger of the two legs, not their sum: they are two sides of one race. This is " +
        "the only depth measure with a history here, and it is the context for every " +
        "probability on the page.");
      window.Chart.line(plot, {
        series: [{ label: "Open interest", points: S.k_dem_oi, color: C.D, width: 2 }],
        yFormat: function (v) { return "$" + Math.round(v / 1000) + "K"; },
        tipFormat: function (v) { return "$" + F.thousands(v); },
        height: 200
      });
    });

    fold("Voter turnout, Kalshi only", function (body) {
      var plot = chart(body, null,
        "Differenced from the nested Above-N thresholds. The two open-ended tails use " +
        "representative values of " + F.thousands(295000) + " and " + F.thousands(385000) +
        ", both judgement calls listed with the other assumptions. Turnout here in 2024 was " +
        "403,314, above the highest quoted threshold.");
      window.Chart.bars(plot, {
        bars: dist.turnout.buckets.map(function (b) {
          return { label: b.label, short: b.label.replace("K-", "-"), value: b.prob,
                   color: "#4A5568",
                   note: "representative point " + F.thousands(b.point) +
                         (b.open_ended ? " (open-ended, assumed)" : "") };
        }),
        yFormat: pct, height: 220
      });
    });

    fold("Pennsylvania Democratic seat count", function (body) {
      var plot = chart(body, null,
        "The whole 17-seat delegation, not this district. Expected " +
        (dist.seats.expected === null ? "n/a" : dist.seats.expected.toFixed(1)) +
        " against a baseline of " + dist.seats.baseline +
        " today. That baseline is hand-entered, so check it against the current delegation " +
        "before leaning on the net-gain reading.");
      window.Chart.bars(plot, {
        bars: dist.seats.brackets.map(function (b) {
          return { label: b.label + " seats", short: b.label.replace("Below ", "<").replace("Above ", ">"),
                   value: b.normalised, color: C.D,
                   note: b.bid_missing ? "no resting bid; mid falls back to half the ask" : "" };
        }),
        yFormat: pct, height: 220
      });
    });

    return sec;
  }

  /* ----------------------------------------------------------------- boot */

  document.addEventListener("data:ready", function (ev) {
    var d = ev.detail, main = document.getElementById("main");
    [headline, probability, modelVsMarket, distribution, marketsVsPolls, secondary]
      .forEach(function (make) {
        try {
          main.appendChild(make(d));
        } catch (err) {
          /* One broken exhibit must not take the page with it. The pipeline
             degrades a missing source to a missing section rather than a failed
             build, and the page follows the same rule. */
          var s = document.createElement("section");
          s.className = "block";
          s.innerHTML = "<div class='caveat high'><b>This section could not be drawn.</b>" +
                        "<p class='num'>" + String(err) + "</p></div>";
          main.appendChild(s);
          if (window.console) console.error(err);
        }
      });
    document.dispatchEvent(new CustomEvent("dashboard:ready", { detail: d }));
  });
})();
