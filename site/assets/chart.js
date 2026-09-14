/* Hand-rolled SVG charts.
 *
 * No charting library. Not because one would not work, but because the four
 * charts that carry this argument each need one specific thing that library
 * defaults get wrong, and fighting a default is more code than drawing the
 * line:
 *
 *   - Gaps must stay gaps. Polymarket lost 11, 9 and 4 days across spring 2026
 *     and Kalshi six more in June-July. Every library's line generator happily
 *     joins the points either side, drawing a straight segment through a week
 *     nobody quoted. Here a run longer than `gapDays` breaks the path.
 *   - A missing value is not zero. Points with no value never enter the array,
 *     and nothing coerces null to 0 on the way to a pixel.
 *   - The 50% reference line is part of the argument, not decoration.
 *   - Colour encodes party and dash encodes venue, which means two series in
 *     the same hue must stay distinguishable at a glance and in greyscale.
 *
 * Everything redraws on resize against the measured container width, so the
 * text stays at its real size instead of being stretched by a viewBox.
 */
(function (global) {
  "use strict";

  var DAY = 86400000;

  function el(name, attrs, text) {
    var n = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (var k in attrs) if (attrs[k] !== null && attrs[k] !== undefined) {
      n.setAttribute(k, attrs[k]);
    }
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function ms(iso) { return Date.parse(iso + "T00:00:00Z"); }

  function niceTicks(lo, hi, count) {
    var span = hi - lo;
    if (!(span > 0)) return [lo];
    var raw = span / Math.max(1, count);
    var mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var norm = raw / mag;
    var step = (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag;
    var out = [], t = Math.ceil(lo / step) * step;
    for (; t <= hi + step * 1e-9; t += step) out.push(Math.round(t / step) * step);
    return out;
  }

  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function timeTicks(lo, hi, width) {
    /* Month starts, thinned until they fit. Dates are the reader's anchor on a
       campaign chart, so the axis is months, never "12 evenly spaced numbers". */
    var out = [], d = new Date(lo);
    d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1));
    if (d.getTime() < lo) d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1));
    while (d.getTime() <= hi) {
      out.push(d.getTime());
      d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1));
    }
    var room = Math.max(1, Math.floor(width / 56));
    var every = Math.ceil(out.length / room);
    return out.filter(function (_, i) { return i % every === 0; }).map(function (t) {
      var dt = new Date(t);
      return { at: t, label: MONTHS[dt.getUTCMonth()] + (dt.getUTCMonth() === 0 ? " " + dt.getUTCFullYear() : "") };
    });
  }

  var fmt = {
    pct: function (v, dp) { return v === null || v === undefined ? "n/a" : (v * 100).toFixed(dp === undefined ? 1 : dp) + "%"; },
    pp: function (v, dp) { return v === null || v === undefined ? "n/a" : (v >= 0 ? "+" : "") + v.toFixed(dp === undefined ? 1 : dp); },
    pts: function (v) { return v === null || v === undefined ? "n/a" : (v > 0 ? "D+" : v < 0 ? "R+" : "") + Math.abs(v).toFixed(1); },
    thousands: function (v) { return v === null || v === undefined ? "n/a" : Math.round(v).toLocaleString("en-US"); },
    day: function (iso) {
      var d = new Date(ms(iso));
      return d.getUTCDate() + " " + MONTHS[d.getUTCMonth()] + " " + d.getUTCFullYear();
    }
  };

  function tipFor(host) {
    var t = host.querySelector(".tip");
    if (!t) { t = document.createElement("div"); t.className = "tip"; host.appendChild(t); }
    return t;
  }

  /* --------------------------------------------------------------- line chart */

  function line(host, opt) {
    var series = (opt.series || []).filter(function (s) { return s.points && s.points.length; });
    host.classList.add("plot");
    var draw = function () {
      var width = Math.max(260, host.clientWidth || 320);
      var narrow = width < 420;
      var height = opt.height || (narrow ? 220 : 280);
      var m = { l: narrow ? 36 : 44, r: 10, t: 10, b: 22 };
      var iw = width - m.l - m.r, ih = height - m.t - m.b;

      var xs = [], ys = [];
      series.forEach(function (s) {
        s.points.forEach(function (p) { xs.push(ms(p[0])); ys.push(p[1]); });
      });
      (opt.markers || []).forEach(function (mk) { xs.push(ms(mk.date)); ys.push(mk.value); });
      if (!xs.length) return;
      var x0 = opt.xMin !== undefined ? ms(opt.xMin) : Math.min.apply(null, xs);
      var x1 = opt.xMax !== undefined ? ms(opt.xMax) : Math.max.apply(null, xs);
      var lo = opt.yMin !== undefined ? opt.yMin : Math.min.apply(null, ys);
      var hi = opt.yMax !== undefined ? opt.yMax : Math.max.apply(null, ys);
      (opt.refLines || []).forEach(function (r) { lo = Math.min(lo, r.y); hi = Math.max(hi, r.y); });
      if (lo === hi) { lo -= 0.5; hi += 0.5; }
      var padY = (hi - lo) * 0.08;
      if (opt.yMin === undefined) lo -= padY;
      if (opt.yMax === undefined) hi += padY;

      var X = function (t) { return m.l + (x1 === x0 ? iw / 2 : (t - x0) / (x1 - x0) * iw); };
      var Y = function (v) { return m.t + ih - (v - lo) / (hi - lo) * ih; };

      var svg = el("svg", { width: width, height: height, viewBox: "0 0 " + width + " " + height,
                            role: "img", "aria-label": opt.aria || opt.title || "chart" });
      if (opt.title) svg.appendChild(el("title", {}, opt.title));

      var ticks = niceTicks(lo, hi, narrow ? 4 : 5);
      var g = el("g", { class: "axis" });
      ticks.forEach(function (v) {
        g.appendChild(el("line", { class: "gridline", x1: m.l, x2: width - m.r, y1: Y(v), y2: Y(v) }));
        g.appendChild(el("text", { x: m.l - 6, y: Y(v) + 3.5, "text-anchor": "end" },
                         (opt.yFormat || fmt.pct)(v, 0)));
      });
      timeTicks(x0, x1, iw).forEach(function (t) {
        g.appendChild(el("text", { x: X(t.at), y: height - 6, "text-anchor": "middle" }, t.label));
      });
      svg.appendChild(g);

      (opt.refLines || []).forEach(function (r) {
        svg.appendChild(el("line", { class: "refline", x1: m.l, x2: width - m.r, y1: Y(r.y), y2: Y(r.y) }));
        if (r.label) svg.appendChild(el("text", { class: "reflabel", x: width - m.r, y: Y(r.y) - 4,
                                                  "text-anchor": "end" }, r.label));
      });

      /* Shaded uncertainty bands, drawn under every line. */
      (opt.bands || []).forEach(function (b) {
        var up = b.upper, dn = b.lower;
        if (!up || !dn || !up.length) return;
        var d = "M" + up.map(function (p) { return X(ms(p[0])) + " " + Y(p[1]); }).join("L") +
                "L" + dn.slice().reverse().map(function (p) { return X(ms(p[0])) + " " + Y(p[1]); }).join("L") + "Z";
        svg.appendChild(el("path", { d: d, fill: b.color, "fill-opacity": b.opacity || 0.12, stroke: "none" }));
      });

      var gapDays = opt.gapDays || 5;
      series.forEach(function (s) {
        /* A dots-only series is how a value that exists but is not a price gets
           shown: present on the chart, deliberately not joined into the line. */
        if (s.dots) {
          s.points.forEach(function (p) {
            svg.appendChild(el("circle", { cx: X(ms(p[0])), cy: Y(p[1]), r: 3.2,
                                           fill: s.fill || "#fff", stroke: s.color,
                                           "stroke-width": 1.4 }));
          });
          return;
        }
        var d = "", prev = null;
        s.points.forEach(function (p) {
          var t = ms(p[0]);
          /* A run of missing days breaks the path. Joining across it draws a
             straight line through a week that was never quoted. */
          d += (prev === null || t - prev > gapDays * DAY ? "M" : "L") + X(t) + " " + Y(p[1]);
          prev = t;
        });
        svg.appendChild(el("path", { d: d, fill: "none", stroke: s.color,
                                     "stroke-width": s.width || 2,
                                     "stroke-dasharray": s.dash || null,
                                     "stroke-linejoin": "round", "stroke-linecap": "round" }));
        var last = s.points[s.points.length - 1];
        if (s.endDot !== false) {
          svg.appendChild(el("circle", { cx: X(ms(last[0])), cy: Y(last[1]), r: 3, fill: s.color }));
        }
      });

      (opt.markers || []).forEach(function (mk) {
        /* A hollow marker (fill white, stroke in the series colour) pairs with
           a dashed line the same way a solid one pairs with a solid line. */
        svg.appendChild(el("circle", { cx: X(ms(mk.date)), cy: Y(mk.value), r: 5,
                                       fill: mk.color, stroke: mk.stroke || "#fff",
                                       "stroke-width": mk.stroke ? 2 : 1.5 }));
        if (mk.label) {
          svg.appendChild(el("text", { class: "reflabel", x: X(ms(mk.date)),
                                       y: Y(mk.value) - 9, "text-anchor": "middle" }, mk.label));
        }
      });

      var cross = el("line", { class: "crosshair", y1: m.t, y2: m.t + ih, x1: -9, x2: -9, opacity: 0 });
      svg.appendChild(cross);
      host.innerHTML = "";
      host.appendChild(svg);
      var tip = tipFor(host);

      function at(clientX) {
        var box = svg.getBoundingClientRect();
        var t = x0 + (clientX - box.left - m.l) / iw * (x1 - x0);
        var best = null;
        series.forEach(function (s) {
          var p = null, gap = Infinity;
          s.points.forEach(function (q) {
            var g2 = Math.abs(ms(q[0]) - t);
            if (g2 < gap) { gap = g2; p = q; }
          });
          if (p && gap < 12 * DAY) {
            if (!best || gap < best.gap) best = { gap: gap, at: p[0] };
            (best.rows = best.rows || []).push({ s: s, p: p, gap: gap });
          }
        });
        if (!best) return null;
        best.rows = best.rows.filter(function (r) { return Math.abs(ms(r.p[0]) - ms(best.at)) <= 3 * DAY; });
        return best;
      }

      function move(ev) {
        var cx = ev.touches ? ev.touches[0].clientX : ev.clientX;
        var hit = at(cx);
        if (!hit) { tip.classList.remove("on"); cross.setAttribute("opacity", 0); return; }
        cross.setAttribute("x1", X(ms(hit.at)));
        cross.setAttribute("x2", X(ms(hit.at)));
        cross.setAttribute("opacity", 1);
        var f = opt.tipFormat || opt.yFormat || fmt.pct;
        tip.innerHTML = "<b>" + fmt.day(hit.at) + "</b>" + hit.rows.map(function (r) {
          return "<br>" + r.s.label + " " + f(r.p[1]) +
                 (r.p[0] !== hit.at ? " <span style='opacity:.6'>(" + r.p[0] + ")</span>" : "");
        }).join("");
        tip.classList.add("on");
        var px = X(ms(hit.at));
        tip.style.left = Math.min(Math.max(4, px - tip.offsetWidth / 2), width - tip.offsetWidth - 4) + "px";
        tip.style.top = (m.t + 2) + "px";
      }
      svg.addEventListener("mousemove", move);
      svg.addEventListener("touchstart", move, { passive: true });
      svg.addEventListener("touchmove", move, { passive: true });
      svg.addEventListener("mouseleave", function () {
        tip.classList.remove("on"); cross.setAttribute("opacity", 0);
      });
    };
    draw();
    observe(host, draw);
    return draw;
  }

  /* -------------------------------------------------------------- bar chart */

  function bars(host, opt) {
    host.classList.add("plot");
    var draw = function () {
      var data = opt.bars || [];
      var width = Math.max(260, host.clientWidth || 320);
      var narrow = width < 460;
      var height = opt.height || (narrow ? 240 : 260);
      var m = { l: narrow ? 34 : 42, r: 10, t: 12, b: narrow ? 46 : 30 };
      var iw = width - m.l - m.r, ih = height - m.t - m.b;
      var vals = data.map(function (b) { return b.value || 0; });
      var hi = opt.yMax !== undefined ? opt.yMax : Math.max.apply(null, vals.concat([0.01])) * 1.12;
      var Y = function (v) { return m.t + ih - v / hi * ih; };
      var step = iw / Math.max(1, data.length);
      var w = Math.max(6, step * 0.68);

      var svg = el("svg", { width: width, height: height, viewBox: "0 0 " + width + " " + height,
                            role: "img", "aria-label": opt.aria || opt.title || "chart" });
      if (opt.title) svg.appendChild(el("title", {}, opt.title));
      var g = el("g", { class: "axis" });
      niceTicks(0, hi, 4).forEach(function (v) {
        g.appendChild(el("line", { class: "gridline", x1: m.l, x2: width - m.r, y1: Y(v), y2: Y(v) }));
        g.appendChild(el("text", { x: m.l - 6, y: Y(v) + 3.5, "text-anchor": "end" },
                        (opt.yFormat || fmt.pct)(v, 0)));
      });
      svg.appendChild(g);

      var tip = tipFor(host);
      data.forEach(function (b, i) {
        var cx = m.l + step * i + step / 2;
        if (b.value === null || b.value === undefined) {
          /* Not quoted is not zero. A hatch-free empty slot with a dash keeps
             the bracket on the axis without asserting a probability for it. */
          svg.appendChild(el("line", { x1: cx - w / 2, x2: cx + w / 2, y1: Y(0), y2: Y(0),
                                       stroke: "var(--ink-3)", "stroke-width": 2 }));
          svg.appendChild(el("text", { class: "reflabel", x: cx, y: Y(0) - 6,
                                       "text-anchor": "middle" }, "n/q"));
        } else {
          var rect = el("rect", { x: cx - w / 2, y: Y(b.value), width: w,
                                  height: Math.max(0.5, Y(0) - Y(b.value)),
                                  fill: b.color, rx: 1.5 });
          svg.appendChild(rect);
        }
        var lab = el("text", { x: cx, y: height - (narrow ? 30 : 12), "text-anchor": "middle",
                               fill: "var(--ink-3)", "font-size": 10 }, b.short || b.label);
        if (narrow) lab.setAttribute("transform", "rotate(-55 " + cx + " " + (height - 30) + ")");
        svg.appendChild(lab);

        var hit = el("rect", { x: m.l + step * i, y: m.t, width: step, height: ih, fill: "transparent" });
        hit.addEventListener("mouseenter", function () {
          tip.innerHTML = "<b>" + b.label + "</b><br>" +
            (opt.yFormat || fmt.pct)(b.value) + (b.note ? "<br>" + b.note : "");
          tip.classList.add("on");
          tip.style.left = Math.min(Math.max(4, cx - 60), width - tip.offsetWidth - 4) + "px";
          tip.style.top = Math.max(0, Y(b.value || 0) - 44) + "px";
        });
        hit.addEventListener("mouseleave", function () { tip.classList.remove("on"); });
        svg.appendChild(hit);
      });
      if (opt.zeroAt !== undefined) {
        var zx = m.l + step * opt.zeroAt;
        svg.appendChild(el("line", { class: "refline", x1: zx, x2: zx, y1: m.t, y2: m.t + ih }));
      }
      host.innerHTML = "";
      host.appendChild(svg);
      host.appendChild(tip);
    };
    draw();
    observe(host, draw);
    return draw;
  }

  /* Redraw against the measured width. A viewBox alone would rescale the text
     with the box, which is how a phone ends up with 6px axis labels. */
  function observe(host, draw) {
    if (global.ResizeObserver) {
      var w = host.clientWidth, ro = new ResizeObserver(function () {
        if (Math.abs(host.clientWidth - w) > 8) { w = host.clientWidth; draw(); }
      });
      ro.observe(host);
    } else {
      global.addEventListener("resize", draw);
    }
  }

  function legend(items) {
    var d = document.createElement("div");
    d.className = "legend";
    items.forEach(function (it) {
      var s = document.createElement("span");
      var i = document.createElement("i");
      if (it.dot) { i.className = "dot"; i.style.background = it.color; }
      else {
        i.style.borderTopColor = it.color;
        if (it.dash) i.style.borderTopStyle = "dashed";
      }
      s.appendChild(i);
      s.appendChild(document.createTextNode(it.label));
      d.appendChild(s);
    });
    return d;
  }

  global.Chart = { line: line, bars: bars, fmt: fmt, legend: legend, ms: ms };
})(window);
