"""
Browser dashboard for the Two Embarcadero Center valuation model.

Run it:   python3 dashboard.py
Then open http://localhost:8642 (it opens automatically). If that port is
already serving a different folder, this one moves to the next free port
and prints the URL it landed on.

Stdlib only — no installs, no internet required. It runs model.py fresh on
every page load, so any edit to model.py or deal.json shows up when you
reload. Three things it adds over the terminal view:

  * an institutional pro-forma and a real sensitivity "tornado" chart
  * a CSV export of the cash flow (writes pro_forma.csv into this folder)
  * an Assumptions section that shows every input, its range, and its source

Stop it with Ctrl+C in the terminal.
"""

import csv
import html
import io
import math
import socket
import threading
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import model

PORT = 8642
HERE = Path(__file__).resolve().parent
CSV_NAME = "pro_forma.csv"
WHOAMI_PATH = "/__whoami"  # reports which folder this server is serving


# ---------------------------------------------------------------- formatting

def money(x):
    """Whole-dollar, e.g. $395,850,000."""
    return f"${x:,.0f}"


def accounting(x):
    """Accounting format: outflows in parentheses, e.g. ($276,150)."""
    return f"(${abs(x):,.0f})" if x < 0 else f"${x:,.0f}"


def pct(x, dp=2):
    """Percent with trailing zeros trimmed: 0.03 -> 3%, 0.0625 -> 6.25%.
    Only strips when there is a decimal point, so 10% never becomes 1%."""
    s = f"{x * 100:.{dp}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return f"{s}%"


def money_compact(x):
    """$355M-style for axis and range labels."""
    return f"${x / 1e6:,.0f}M"


def fmt_value(key, v):
    """Format a single assumption value by inferring its kind from the key.

    Known inputs format cleanly; anything an attendee adds later (e.g. a debt
    input) still gets a reasonable format from the same rules."""
    if isinstance(v, str):
        return html.escape(v)
    if "psf" in key:
        return f"${v:,.2f} / SF"
    if "_pct" in key:
        return pct(v) + (" of EGI" if key.endswith("_egi") else "")
    if "year" in key:
        return f"{v:g} years"
    if "month" in key:
        return f"{v:g} months"
    if abs(v) >= 10000:
        return money(v)
    return f"{v:g}"


def fmt_range(key, lo, hi):
    """Format a declared [low, high] range in the same units as the value."""
    if "psf" in key:
        return f"${lo:,.0f} – ${hi:,.0f} / SF"
    if "_pct" in key:
        return f"{pct(lo)} – {pct(hi)}"
    if abs(hi) >= 1_000_000:
        return f"{money_compact(lo)} – {money_compact(hi)}"
    return f"{lo:g} – {hi:g}"


# ---------------------------------------------------------------- sections

def kpi_band(deal, returns):
    """Returns band: the hero IRR plus five supporting metrics, each with a
    one-line plain-English note (this audience is new to DCFs)."""
    sf = deal["property"]["rentable_sf"]
    basis, em = returns["basis"], returns["equity_multiple"]
    exitv, gic = returns["exit_value"], returns["going_in_cap"]
    exit_cap = model.val(deal, "exit", "exit_cap_pct")
    irr = returns["irr"]
    irr_str = pct(irr) if irr is not None else "n/a"
    bps_inside = round((gic - exit_cap) * 10000)

    kpis = [
        ("Equity multiple", f"{em:.2f}x", ""),
        ("Basis", f"${basis / 1e6:,.1f}M",
         f"${basis / sf:,.0f}/SF all-in · incl. 1.5% closing"),
        ("Year 1 yield on cost", pct(gic),
         "Year-1 NOI ÷ total basis"),
        ("Exit value", f"${exitv / 1e6:,.1f}M",
         f"${exitv / sf:,.0f}/SF · net of 1.75% sale cost"),
        ("Exit cap", pct(exit_cap),
         f"on forward NOI · {bps_inside} bps inside Year-1 yield"),
    ]
    cells = "".join(
        f"<div class='kpi'><div class='k'>{html.escape(k)}</div>"
        f"<div class='v'>{v}</div>"
        + (f"<div class='kn'>{html.escape(n)}</div>" if n else "")
        + "</div>"
        for k, v, n in kpis
    )
    return f"""
  <div class="kpiband">
    <div class="kpi-hero">
      <div class="k">Unlevered IRR</div>
      <div class="hero-v">{irr_str}</div>
      <div class="hero-note">The annualized return over the five-year hold,
        before any financing — the headline number the whole model exists to
        answer.</div>
    </div>
    <div class="kpi-grid">{cells}</div>
  </div>"""


def proforma_table(deal, rows):
    """Institutional pro-forma: right-aligned tabular figures, a broken-out
    capital-reserves line (shown as an outflow in accounting parentheses),
    a gold cash-flow column, and a cumulative total rule."""
    sf = deal["property"]["rentable_sf"]
    reserves = model.val(deal, "capital", "reserves_psf") * sf  # constant/yr

    body = ""
    tot = {"egi": 0.0, "noi": 0.0, "res": 0.0, "cf": 0.0}
    for r in rows:
        tot["egi"] += r["egi"]; tot["noi"] += r["noi"]
        tot["res"] += reserves; tot["cf"] += r["cash_flow"]
        body += (
            f"<tr><td class='yr'>Year {r['year']}</td>"
            f"<td>${r['rent_psf']:,.2f}</td>"
            f"<td>{r['occupancy']:.1%}</td>"
            f"<td>{money(r['egi'])}</td>"
            f"<td class='noi'>{money(r['noi'])}</td>"
            f"<td class='neg'>{accounting(-reserves)}</td>"
            f"<td class='cf'>{money(r['cash_flow'])}</td></tr>"
        )
    foot = (
        f"<tr class='total'><td>Cumulative · Yrs 1–5</td><td>—</td><td>—</td>"
        f"<td>{money(tot['egi'])}</td><td class='noi'>{money(tot['noi'])}</td>"
        f"<td class='neg'>{accounting(-tot['res'])}</td>"
        f"<td class='cf'>{money(tot['cf'])}</td></tr>"
    )
    return f"""
  <div class="table-wrap">
  <table class="pf">
    <thead><tr>
      <th class="yr">Year</th><th>Rent PSF</th><th>Occupancy</th>
      <th>EGI</th><th class="noi">NOI</th><th>Cap. reserves</th>
      <th class="cf">Cash flow</th>
    </tr></thead>
    <tbody>{body}</tbody>
    <tfoot>{foot}</tfoot>
  </table>
  </div>
  <p class="note"><b>How to read this.</b> Cash flow = NOI less capital
  reserves of ${reserves:,.0f}/yr; figures in (parentheses) are outflows.
  The reversion — {money(model.run(deal)[1]['exit_value'])} from a Year-5
  forward NOI at the exit cap, net of sale costs — is realized at exit and is
  not shown as an operating line above.</p>"""


def tornado_svg(base_irr, sens):
    """A real horizontal tornado, drawn as inline SVG (no chart library).

    Each bar spans the IRR outcome as one input is swept across its declared
    range, split at the base case: the downside leg (dim) left of base, the
    upside leg (bright gold) right of base. Sorted widest-swing first."""
    lo = min(s["low_irr"] for s in sens)
    hi = max(s["high_irr"] for s in sens)
    dmin = math.floor(lo / 0.02) * 0.02          # nice 2% gridlines
    dmax = math.ceil(hi / 0.02) * 0.02
    dmin = min(dmin, base_irr); dmax = max(dmax, base_irr)

    # geometry (viewBox units; the SVG scales to container width)
    W, labelW, deltaW, padT, rowH, padB = 960, 232, 96, 64, 42, 30
    x0, x1 = labelW, W - deltaW
    plotW = x1 - x0
    H = padT + len(sens) * rowH + padB

    def X(v):
        return x0 + (v - dmin) / (dmax - dmin) * plotW

    parts = [f'<svg class="tornado" viewBox="0 0 {W} {H}" '
             f'role="img" aria-label="Sensitivity tornado">']

    # gridlines + axis ticks (every 2%)
    t = dmin
    while t <= dmax + 1e-9:
        gx = X(t)
        parts.append(f'<line class="grid" x1="{gx:.1f}" y1="{padT-12}" '
                     f'x2="{gx:.1f}" y2="{H-padB}"/>')
        parts.append(f'<text class="axis" x="{gx:.1f}" y="{padT-20}" '
                     f'text-anchor="middle">{pct(t,0)}</text>')
        t += 0.02

    # base-case line
    bx = X(base_irr)
    parts.append(f'<line class="baseline" x1="{bx:.1f}" y1="{padT-12}" '
                 f'x2="{bx:.1f}" y2="{H-padB}"/>')
    parts.append(f'<text class="baselbl" x="{bx:.1f}" y="{padT-30}" '
                 f'text-anchor="middle">BASE {pct(base_irr)}</text>')

    # column headers
    parts.append(f'<text class="head" x="{x0-14}" y="{padT-30}" '
                 f'text-anchor="end">INPUT</text>')
    parts.append(f'<text class="head" x="{W}" y="{padT-30}" '
                 f'text-anchor="end">Δ IRR</text>')

    for i, s in enumerate(sens):
        cy = padT + i * rowH + rowH / 2
        bh = 15
        lx, rx = X(s["low_irr"]), X(s["high_irr"])
        # downside leg (low -> base) and upside leg (base -> high)
        dn_l, dn_r = min(lx, bx), bx
        up_l, up_r = bx, max(rx, bx)
        parts.append(f'<rect class="bar-dn" x="{dn_l:.1f}" y="{cy-bh/2:.1f}" '
                     f'width="{max(0, dn_r-dn_l):.1f}" height="{bh}" rx="2"/>')
        parts.append(f'<rect class="bar-up" x="{up_l:.1f}" y="{cy-bh/2:.1f}" '
                     f'width="{max(0, up_r-up_l):.1f}" height="{bh}" rx="2"/>')
        # input label (left, shortened for the chart) and swing (right)
        short = s["label"].split(" (")[0]
        parts.append(f'<text class="name" x="{x0-14}" y="{cy+4:.1f}" '
                     f'text-anchor="end">{html.escape(short)}</text>')
        parts.append(f'<text class="swing" x="{W}" y="{cy+4:.1f}" '
                     f'text-anchor="end">{pct(s["swing"])}</text>')
        # endpoint IRR values just outside the bar
        parts.append(f'<text class="end" x="{lx-6:.1f}" y="{cy+4:.1f}" '
                     f'text-anchor="end">{pct(s["low_irr"])}</text>')
        parts.append(f'<text class="end" x="{rx+6:.1f}" y="{cy+4:.1f}" '
                     f'text-anchor="start">{pct(s["high_irr"])}</text>')

    parts.append('</svg>')
    return "\n".join(parts)


def assumptions_section(deal, sens):
    """Every input: value, declared range, and sourcing basis. The two widest
    swings get a small rank tag — the transparency argument, made visible."""
    swing_by_label = {s["label"]: s["swing"] for s in sens}
    ranked = [s["label"] for s in sens]  # already sorted widest-first

    rows = ""
    for section, contents in deal.items():
        if not isinstance(contents, dict):
            continue
        for key, spec in contents.items():
            if not (isinstance(spec, dict) and "value" in spec):
                continue
            label = spec.get("label", key)
            value = fmt_value(key, spec["value"])
            rng = ""
            if "range" in spec:
                lo, hi = spec["range"]
                rng = f"<span class='range'>range {fmt_range(key, lo, hi)}</span>"
            tag = ""
            if label in swing_by_label:
                rank = ranked.index(label)
                sw = swing_by_label[label]
                cls = "tag hot" if rank == 0 else ("tag warm" if rank == 1 else "tag")
                note = ("#1 driver" if rank == 0 else
                        "#2 driver" if rank == 1 else f"Δ IRR {pct(sw)}")
                tag = f"<span class='{cls}'>{note}</span>"
            basis = html.escape(spec.get("basis", ""))
            rows += (
                f"<div class='arow'>"
                f"<div class='ainput'>{html.escape(label)} {tag}</div>"
                f"<div class='avalue'><b>{value}</b>{rng}</div>"
                f"<div class='abasis'>{basis}</div>"
                f"</div>"
            )
    return f"""
  <div class="atable">
    <div class="ahead"><div>Input</div><div>Value / range</div>
      <div>Basis</div></div>
    {rows}
  </div>"""


# ---------------------------------------------------------------- CSV export

def write_csv(deal, rows):
    """Write the pro-forma to pro_forma.csv in this folder and return the text.
    Uses the stdlib csv module — no dependencies."""
    sf = deal["property"]["rentable_sf"]
    reserves = model.val(deal, "capital", "reserves_psf") * sf
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Year", "Rent PSF", "Occupancy",
                "EGI", "NOI", "Capital reserves", "Cash flow"])
    for r in rows:
        w.writerow([r["year"], round(r["rent_psf"], 2), round(r["occupancy"], 4),
                    round(r["egi"]), round(r["noi"]),
                    -round(reserves), round(r["cash_flow"])])
    w.writerow(["Cumulative",
                "", "",
                round(sum(r["egi"] for r in rows)),
                round(sum(r["noi"] for r in rows)),
                -round(reserves * len(rows)),
                round(sum(r["cash_flow"] for r in rows))])
    text = buf.getvalue()
    (HERE / CSV_NAME).write_text(text)
    return text


# ---------------------------------------------------------------- page

def render_page():
    """Run the model fresh and render the whole dashboard as one HTML page."""
    deal = model.load_deal()
    rows, returns = model.run(deal)
    base, sens = model.sensitivity(deal)

    p = deal["property"]
    hold = model.val(deal, "acquisition", "hold_years")
    stamp = datetime.now()
    stamp_str = stamp.strftime("%b %d, %Y") + " · " + \
        stamp.strftime("%I:%M %p").lstrip("0")

    # optional property photo — degrade gracefully if it isn't there
    photo = ""
    if (HERE / "property.jpg").exists():
        photo = ('<div class="hero-photo">'
                 '<img src="/property.jpg" alt="Property photograph"></div>')

    name = html.escape(p["name"])
    subline = (f"{html.escape(p['city'])} &middot; {html.escape(p['type'])} "
               f"&middot; {p['rentable_sf']:,} SF &middot; {hold}-year hold "
               f"&middot; <b>unlevered</b>")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} — Valuation</title>
<style>{CSS}</style></head>
<body>
<div class="topbar"></div>
<div class="wrap">

  <div class="util">
    <div class="brandmark"><span class="dot"></span>
      <span class="kick">Investment Committee Tearsheet</span></div>
    <div class="util-actions">
      <span class="lastrun">Last run <b>{stamp_str}</b></span>
      <a class="btn" href="/{CSV_NAME}" download>&#8595; Download CSV</a>
      <button class="btn btn-primary" onclick="location.reload()">
        &#8635; Re-run model</button>
    </div>
  </div>

  <header class="masthead">
    <div class="mast-text">
      <div class="eyebrow">Single-asset valuation</div>
      <h1 class="propname">{name}</h1>
      <div class="subline">{subline}</div>
    </div>
    {photo}
  </header>

  <section class="section">
    <div class="sec-head"><div class="sec-left">
      <span class="sec-idx">01</span><span class="sec-title">Returns</span>
    </div><span class="sec-sub">unlevered &middot; net to equity &middot;
      {hold}-year hold</span></div>
    {kpi_band(deal, returns)}
  </section>

  <section class="section">
    <div class="sec-head"><div class="sec-left">
      <span class="sec-idx">02</span>
      <span class="sec-title">Pro-forma cash flow</span>
    </div><span class="sec-sub">USD &middot; unlevered &middot;
      lease-up to stabilization</span></div>
    {proforma_table(deal, rows)}
  </section>

  <section class="section">
    <div class="sec-head"><div class="sec-left">
      <span class="sec-idx">03</span><span class="sec-title">Sensitivity</span>
    </div><span class="sec-sub">ranked by impact on IRR</span></div>
    <p class="lead">Each bar spans the unlevered IRR as one input is swept
      across its full declared range, holding everything else at the base case
      of {pct(base['irr'])}. The dim leg is the downside, the gold leg the
      upside; sorted by the size of the swing, widest first.</p>
    <div class="legend">
      <span class="li"><span class="sw sw-dn"></span>Downside of base</span>
      <span class="li"><span class="sw sw-up"></span>Upside of base</span>
      <span class="li"><span class="sw sw-base"></span>Base case
        {pct(base['irr'])}</span>
    </div>
    <div class="tornado-wrap">{tornado_svg(base['irr'], sens)}</div>
  </section>

  <section class="section">
    <div class="sec-head"><div class="sec-left">
      <span class="sec-idx">04</span><span class="sec-title">Assumptions</span>
    </div><span class="sec-sub">every input, its range, and where it came
      from</span></div>
    {assumptions_section(deal, sens)}
    <p class="note">Illustrative assumptions for a real building — not its
      actual economics, and not investment advice. Full citations in
      <code>SOURCES.md</code>; edit any input in <code>deal.json</code> and
      hit re-run.</p>
  </section>

  <footer class="brand">Built at Claude Code for Real Estate &middot;
    <a href="https://lauriesartain.com/claude">lauriesartain.com/claude</a>
  </footer>

</div></body></html>"""


# ---------------------------------------------------------------- styles

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;600;700&family=Inter:wght@400;500;600;700&display=swap');
:root{
  --bg:#0a0a0a; --panel:#141414; --line:#262626; --ink:#ededed; --muted:#9a9a9a;
  --gold:#c9a227; --gold-dim:rgba(201,162,39,.32); --gold-faint:rgba(201,162,39,.07);
  --hair:rgba(255,255,255,.05); --neg:#d98a8a;
  --disp:'Playfair Display',Georgia,'Times New Roman',serif;
  --body:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--body);
  font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased;
  text-rendering:optimizeLegibility;overflow-x:hidden}
.num{font-variant-numeric:tabular-nums lining-nums}
a{color:var(--gold);text-decoration:none;border-bottom:1px solid var(--gold-dim)}
a:hover{border-bottom-color:var(--gold)}
b,strong{font-weight:600}
.topbar{height:3px;background:linear-gradient(90deg,var(--gold),var(--gold-dim) 42%,transparent 72%)}
.wrap{max-width:1160px;margin:0 auto;padding:24px 32px 48px}

.util{display:flex;justify-content:space-between;align-items:center;gap:16px;
  flex-wrap:wrap;margin-bottom:26px}
.brandmark{display:flex;align-items:center;gap:10px}
.dot{width:9px;height:9px;border-radius:50%;background:var(--gold);
  box-shadow:0 0 0 3px rgba(201,162,39,.14);flex:none}
.kick{font-size:11px;letter-spacing:.2em;text-transform:uppercase;
  color:var(--muted);font-weight:600}
.util-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.lastrun{font-size:11.5px;color:var(--muted);white-space:nowrap}
.lastrun b{color:var(--ink);font-weight:600}
.btn{display:inline-flex;align-items:center;gap:7px;cursor:pointer;
  border:1px solid var(--line);background:transparent;color:var(--ink);
  padding:8px 13px;border-radius:4px;font:600 12px var(--body);white-space:nowrap}
.btn:hover{border-color:var(--gold);color:var(--gold)}
.btn-primary{border-color:rgba(201,162,39,.55);color:var(--gold)}
.btn-primary:hover{background:var(--gold-faint)}

.masthead{display:flex;justify-content:space-between;align-items:flex-end;
  gap:28px;margin:6px 0 34px}
.eyebrow{color:var(--gold);letter-spacing:.22em;font-size:11px;font-weight:600;
  text-transform:uppercase}
.propname{font-family:var(--disp);font-weight:600;
  font-size:clamp(30px,5.4vw,50px);line-height:1.02;letter-spacing:-.01em;
  margin:10px 0 12px}
.subline{color:var(--muted);font-size:13.5px}
.subline b{color:var(--ink)}
.hero-photo{flex:none;width:min(320px,38vw)}
.hero-photo img{width:100%;height:180px;object-fit:cover;border-radius:6px;
  border:1px solid var(--line)}

.section{margin-bottom:34px}
.sec-head{display:flex;align-items:baseline;justify-content:space-between;
  gap:16px;flex-wrap:wrap;margin:0 0 16px;border-bottom:1px solid var(--line);
  padding-bottom:10px}
.sec-left{display:flex;align-items:baseline;gap:12px}
.sec-idx{color:var(--gold);font-weight:600;font-size:12px;letter-spacing:.14em}
.sec-title{font-weight:600;font-size:13px;text-transform:uppercase;
  letter-spacing:.14em}
.sec-sub{color:var(--muted);font-size:12px}
.lead{color:var(--muted);font-size:13px;max-width:70ch;margin:0 0 14px}

/* returns band */
.kpiband{display:grid;grid-template-columns:minmax(260px,1fr) 2.15fr;
  border:1px solid var(--line);background:var(--panel);border-radius:6px;
  overflow:hidden}
.kpi-hero{padding:24px 28px;border-right:1px solid var(--line)}
.kpi-hero .k{font-size:11px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--muted);font-weight:600}
.hero-v{font-size:clamp(44px,6.4vw,66px);font-weight:600;color:var(--gold);
  line-height:1;letter-spacing:-.02em;margin:10px 0 12px;
  font-variant-numeric:tabular-nums}
.hero-note{color:var(--muted);font-size:12px;line-height:1.5;max-width:34ch}
.kpi-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));
  gap:1px;background:var(--line)}
.kpi{background:var(--panel);padding:15px 16px;min-width:0}
.kpi .k{font-size:10px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--muted);font-weight:600}
.kpi .v{font-size:21px;font-weight:600;margin:7px 0 5px;letter-spacing:-.01em;
  white-space:nowrap;font-variant-numeric:tabular-nums}
.kpi .kn{font-size:10.5px;color:var(--muted);line-height:1.4}

/* pro-forma */
.table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
table.pf{width:100%;min-width:660px;border-collapse:collapse;
  font-variant-numeric:tabular-nums lining-nums}
.pf th,.pf td{padding:10px 14px;text-align:right;white-space:nowrap}
.pf th.yr,.pf td.yr{text-align:left}
.pf thead th{font-size:10.5px;font-weight:600;text-transform:uppercase;
  letter-spacing:.09em;color:var(--muted);
  border-bottom:1.5px solid var(--gold-dim);padding-bottom:9px}
.pf tbody td{font-size:13.5px;color:var(--muted);border-bottom:1px solid var(--hair)}
.pf tbody td.yr{color:var(--ink);font-weight:600}
.pf td.noi,.pf th.noi{color:var(--ink)}
.pf td.noi{font-weight:600}
.pf td.cf,.pf th.cf{color:var(--gold);background:var(--gold-faint)}
.pf td.cf{font-weight:600}
.pf td.neg{color:var(--neg)}
.pf tfoot td{font-size:13px;font-weight:700;color:var(--ink);
  border-top:1.5px solid var(--line);padding-top:12px}
.pf tfoot td:first-child{font-size:10.5px;text-transform:uppercase;
  letter-spacing:.09em;color:var(--muted);font-weight:600}
.note{color:var(--muted);font-size:11.5px;line-height:1.55;margin:14px 0 0;
  max-width:78ch}
.note b{color:var(--ink)}

/* tornado */
.legend{display:flex;gap:18px;flex-wrap:wrap;margin:0 0 8px}
.legend .li{display:flex;align-items:center;gap:7px;font-size:11px;
  color:var(--muted)}
.sw{width:22px;height:11px;border-radius:2px;display:inline-block}
.sw-up{background:var(--gold)}
.sw-dn{background:var(--gold-dim)}
.sw-base{width:2px;height:13px;border-radius:0;background:var(--gold)}
.tornado-wrap{width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}
.tornado{display:block;width:100%;min-width:600px;height:auto}
.tornado .name{fill:var(--ink);font:600 13px var(--body)}
.tornado .swing{fill:var(--gold);font:700 13px var(--body);
  font-variant-numeric:tabular-nums}
.tornado .end{fill:var(--muted);font:500 10.5px var(--body);
  font-variant-numeric:tabular-nums}
.tornado .axis{fill:var(--muted);font:500 10.5px var(--body);
  font-variant-numeric:tabular-nums}
.tornado .head{fill:var(--muted);font:600 10px var(--body);letter-spacing:.11em}
.tornado .baselbl{fill:var(--gold);font:600 10px var(--body);letter-spacing:.08em}
.tornado .grid{stroke:var(--line);stroke-width:1}
.tornado .baseline{stroke:var(--gold);stroke-width:1.25;stroke-dasharray:3 3;
  opacity:.75}
.tornado .bar-up{fill:var(--gold)}
.tornado .bar-dn{fill:var(--gold-dim)}

/* assumptions */
.atable{border-top:1px solid var(--line)}
.ahead,.arow{display:grid;grid-template-columns:1.1fr 1fr 2.2fr;gap:20px;
  padding:13px 4px;border-bottom:1px solid var(--hair)}
.ahead{font-size:10px;letter-spacing:.11em;text-transform:uppercase;
  color:var(--muted);font-weight:600;border-bottom:1px solid var(--line)}
.ainput{font-weight:600;color:var(--ink);display:flex;flex-wrap:wrap;
  align-items:center;gap:8px}
.avalue b{display:block;font-variant-numeric:tabular-nums}
.avalue .range{display:block;color:var(--muted);font-size:11.5px;margin-top:3px}
.abasis{color:var(--muted);font-size:12px;line-height:1.5}
.tag{font-size:9.5px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;
  color:var(--muted);border:1px solid var(--line);border-radius:999px;
  padding:2px 8px;white-space:nowrap}
.tag.hot{color:var(--gold);border-color:var(--gold-dim);background:var(--gold-faint)}
.tag.warm{color:var(--gold);border-color:var(--gold-dim)}

.brand{margin-top:40px;padding-top:16px;border-top:1px solid var(--line);
  color:var(--muted);font-size:12px}
.brand a{color:var(--gold)}

/* phone */
@media (max-width:720px){
  .wrap{padding:20px 18px 40px}
  .util{flex-direction:column;align-items:flex-start;gap:12px}
  .util-actions{width:100%;flex-direction:column;align-items:stretch;gap:8px}
  .util-actions .btn{width:100%;justify-content:center}
  .masthead{flex-direction:column;align-items:stretch}
  .hero-photo{width:100%}
  .hero-photo img{height:150px}
  .kpiband{grid-template-columns:1fr}
  .kpi-hero{border-right:0;border-bottom:1px solid var(--line)}
  .kpi-grid{grid-template-columns:repeat(2,1fr)}
  .ahead{display:none}
  .arow{grid-template-columns:1fr;gap:5px;padding:14px 4px}
  .avalue b{display:inline}
  .avalue .range{display:inline;margin-left:8px}
}

/* print — light, paginated, no interactive chrome */
@media print{
  @page{margin:14mm}
  body{background:#fff;color:#111;overflow:visible}
  .topbar,.util-actions{display:none}
  .wrap{max-width:none;padding:0}
  a{color:#111;border:0}
  .panel,.kpiband,.kpi,.kpi-grid,.kpi-hero{background:#fff!important;
    border-color:#ddd!important}
  .kpiband,.kpi-grid{gap:0}
  .eyebrow,.sec-idx,.kick,.hero-v,.brand a,.tag.hot,.tag.warm{color:#8a6b14!important}
  .pf td.cf,.pf th.cf{background:#faf6e8!important;color:#8a6b14!important}
  .kpi,.kpi-hero{border:1px solid #ddd!important}
  .sec-head{border-color:#ccc}
  .tornado .name,.pf tbody td.yr,.pf td.noi,.kpi .v{fill:#111;color:#111}
  .section{break-inside:avoid}
  .tornado .bar-up{fill:#c9a227}.tornado .bar-dn{fill:#e6d79a}
  /* shrink the wide pieces so nothing (esp. the cash-flow column) clips on paper */
  .table-wrap,.tornado-wrap{overflow:visible}
  table.pf{min-width:0}
  .pf{font-size:9.5px}
  .pf th,.pf td{padding:5px 7px}
  .kpi .v{font-size:15px}
  .kpi .kn{font-size:8.5px}
  .tornado{min-width:0}
}
"""


# ---------------------------------------------------------------- server

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        try:
            if path == WHOAMI_PATH:
                self._send(200, str(HERE).encode("utf-8"),
                           "text/plain; charset=utf-8")
            elif path == "/" + CSV_NAME:
                deal = model.load_deal()
                rows, _ = model.run(deal)
                body = write_csv(deal, rows).encode("utf-8")
                self._send(200, body, "text/csv; charset=utf-8",
                           {"Content-Disposition":
                            f'attachment; filename="{CSV_NAME}"'})
            elif path == "/property.jpg" and (HERE / "property.jpg").exists():
                self._send(200, (HERE / "property.jpg").read_bytes(),
                           "image/jpeg")
            else:
                self._send(200, render_page().encode("utf-8"),
                           "text/html; charset=utf-8")
        except Exception as e:
            # keep the error page readable and point at the fix
            msg = (
                "<!DOCTYPE html><meta charset='utf-8'>"
                "<body style='background:#0a0a0a;color:#ededed;"
                "font:15px/1.6 -apple-system,Segoe UI,sans-serif;"
                "max-width:640px;margin:12vh auto;padding:0 24px'>"
                "<h1 style='font-family:Georgia,serif;color:#c9a227'>"
                "The model hit an error</h1>"
                f"<pre style='background:#141414;border:1px solid #262626;"
                f"border-left:3px solid #c9a227;padding:14px;border-radius:6px;"
                f"white-space:pre-wrap;color:#d98a8a'>{html.escape(str(e))}</pre>"
                "<p>Paste that message into Claude Code and ask it to fix the "
                "error, then refresh this page. Nothing is broken permanently — "
                "<code>git checkout .</code> resets everything.</p>"
                "</body>"
            ).encode("utf-8")
            self._send(500, msg, "text/html; charset=utf-8")

    def log_message(self, *args):
        pass  # keep the terminal quiet


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def folder_on_port(port):
    """The folder the dashboard on `port` serves, or None if it isn't ours."""
    try:
        url = f"http://127.0.0.1:{port}{WHOAMI_PATH}"
        with urllib.request.urlopen(url, timeout=1.0) as r:
            text = r.read(500).decode("utf-8", "replace").strip()
        # some other server could answer anything; only trust a real folder
        return text if text and Path(text).is_dir() else None
    except Exception:
        return None


def first_free_port(start, tries=10):
    for port in range(start, start + tries):
        if not port_in_use(port):
            return port
    return None


def main():
    port = PORT
    if port_in_use(port):
        running = folder_on_port(port)
        if running == str(HERE):
            # this folder's own dashboard — reuse it rather than double up
            print(f"This folder's dashboard is already running at "
                  f"http://localhost:{port}")
            print("Opening it in your browser. Click \"Re-run model\" there to")
            print("pick up your edits — no need to restart the server.")
            webbrowser.open(f"http://localhost:{port}")
            return

        # something else holds the port. Serving it would show the wrong
        # folder's numbers and quietly ignore edits made here, so move over.
        whose = running or "another program (not a dashboard)"
        port = first_free_port(PORT + 1)
        if port is None:
            print(f"Port {PORT} is taken by {whose}, and ports "
                  f"{PORT + 1}-{PORT + 10} are all busy too.")
            print("Stop that server, then run this again.")
            return
        print(f"Port {PORT} is taken by {whose}.")
        print(f"Starting this folder's dashboard on port {port} instead.")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}"
    print(f"Dashboard running at {url}")
    print(f"Serving {HERE}")
    print("Press Ctrl+C to stop.")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
