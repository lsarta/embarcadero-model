"""
Browser dashboard for the Embarcadero valuation model.

Run it:   python3 dashboard.py
Then open http://localhost:8642 (it will try to open automatically).

Stdlib only — no installs. Serves one page rendering the model's output:
cash flow table, returns, and the sensitivity ranking. Re-runs the model
on every refresh, so changes to model.py or deal.json show up when you
reload the page.

Stop it with Ctrl+C in the terminal.
"""

import html
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import model

PORT = 8642


def fmt_money(x):
    return f"${x:,.0f}"


def render_page():
    """Run the model fresh and render everything as one HTML page."""
    deal = model.load_deal()
    rows, returns = model.run(deal)
    base, sens = model.sensitivity(deal)

    p = deal["property"]
    hold = model.val(deal, "acquisition", "hold_years")

    cash_rows = ""
    for r in rows:
        cash_rows += (
            f"<tr><td>{r['year']}</td>"
            f"<td class='num'>{r['rent_psf']:.2f}</td>"
            f"<td class='num'>{r['occupancy']:.1%}</td>"
            f"<td class='num'>{fmt_money(r['egi'])}</td>"
            f"<td class='num'>{fmt_money(r['noi'])}</td>"
            f"<td class='num'>{fmt_money(r['cash_flow'])}</td></tr>"
        )

    widest = sens[0]["swing"] if sens else 1
    sens_rows = ""
    for s in sens:
        lo, hi = s["low_input"], s["high_input"]
        if hi <= 1.0:
            rng = f"{lo:.2%} – {hi:.2%}"
        elif hi < 1000:
            rng = f"{lo:,.2f} – {hi:,.2f}"
        else:
            rng = f"${lo/1e6:,.0f}M – ${hi/1e6:,.0f}M"
        pct = max(3, round(s["swing"] / widest * 100))
        sens_rows += (
            f"<tr><td>{html.escape(s['label'])}</td>"
            f"<td class='num'>{rng}</td>"
            f"<td class='num'>{s['low_irr']:.2%} – {s['high_irr']:.2%}</td>"
            f"<td class='num'>{s['swing']:.2%}</td></tr>"
            f"<tr class='barrow'><td colspan='4'>"
            f"<div class='bar' style='width:{pct}%'></div></td></tr>"
        )

    irr = returns["irr"]
    irr_str = f"{irr:.2%}" if irr is not None else "n/a"

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(p['name'])} — Valuation</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Playfair+Display:wght@500;600&display=swap');
  :root {{
    --bg: #0a0a0a; --panel: #141414; --line: #262626;
    --ink: #ededed; --muted: #9a9a9a; --gold: #c9a227;
  }}
  * {{ box-sizing: border-box; }}
  body {{ font: 15px/1.55 Inter, -apple-system, 'Segoe UI', sans-serif;
         margin: 0; background: var(--bg); color: var(--ink);
         padding: 2.5rem 1.25rem 4rem; }}
  .wrap {{ max-width: 880px; margin: 0 auto; }}
  h1 {{ font-family: 'Playfair Display', Georgia, serif; font-weight: 600;
       font-size: 1.9rem; letter-spacing: .01em; margin: 0 0 .3rem; }}
  .sub {{ color: var(--muted); margin: 0 0 2.25rem; font-size: .92rem; }}
  .sub .tag {{ color: var(--gold); }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px,1fr));
            gap: .8rem; margin-bottom: 2.25rem; }}
  .card {{ background: var(--panel); border: 1px solid var(--line);
           border-radius: 10px; padding: 1rem 1.1rem; }}
  .card .k {{ font-size: .68rem; text-transform: uppercase; letter-spacing: .12em;
              color: var(--muted); margin-bottom: .35rem; }}
  .card .v {{ font-size: 1.45rem; font-weight: 600;
              font-variant-numeric: tabular-nums; }}
  .card.hero {{ border-color: var(--gold); }}
  .card.hero .v {{ color: var(--gold); font-size: 1.7rem; }}
  h2 {{ font-family: 'Playfair Display', Georgia, serif; font-weight: 500;
       font-size: 1.15rem; margin: 2.25rem 0 .7rem; }}
  h2::after {{ content: ""; display: block; height: 1px; margin-top: .45rem;
              background: linear-gradient(90deg, var(--gold), transparent 60%); }}
  table {{ width: 100%; border-collapse: collapse; background: var(--panel);
           border: 1px solid var(--line); border-radius: 10px; overflow: hidden;
           font-size: .9rem; }}
  th, td {{ padding: .55rem .75rem; text-align: left;
            border-bottom: 1px solid var(--line); }}
  th {{ background: #1b1b1b; font-size: .68rem; text-transform: uppercase;
        letter-spacing: .1em; color: var(--muted); font-weight: 500; }}
  tr:last-child td {{ border-bottom: 0; }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  tr.barrow td {{ border-bottom: 1px solid var(--line); padding: 0 .75rem .55rem; }}
  .bar {{ height: 6px; background: linear-gradient(90deg, var(--gold), #8a6b14);
         border-radius: 3px; }}
  .foot {{ margin-top: 2.5rem; color: var(--muted); font-size: .82rem; }}
  .brand {{ margin-top: 2.75rem; padding-top: 1.1rem; border-top: 1px solid var(--line);
           color: var(--muted); font-size: .82rem; letter-spacing: .02em; }}
  .brand a {{ color: var(--gold); text-decoration: none; }}
  .refresh {{ position: fixed; top: 1rem; right: 1rem; background: var(--gold);
              color: #0a0a0a; border: 0; border-radius: 7px; padding: .55rem 1rem;
              font-size: .85rem; font-weight: 600; cursor: pointer;
              font-family: Inter, sans-serif; }}
  .refresh:hover {{ filter: brightness(1.08); }}
</style></head><body>
<button class="refresh" onclick="location.reload()">↻ Re-run model</button>
<div class="wrap">
<h1>{html.escape(p['name'])}</h1>
<p class="sub">{html.escape(p['city'])} · {html.escape(p['type'])} ·
{p['rentable_sf']:,} SF · {hold}-year hold · <span class="tag">unlevered</span></p>

<div class="cards">
  <div class="card hero"><div class="k">Unlevered IRR</div>
    <div class="v">{irr_str}</div></div>
  <div class="card"><div class="k">Equity multiple</div>
    <div class="v">{returns['equity_multiple']:.2f}x</div></div>
  <div class="card"><div class="k">Basis</div>
    <div class="v">{fmt_money(returns['basis'])}</div></div>
  <div class="card"><div class="k">Going-in cap</div>
    <div class="v">{returns['going_in_cap']:.2%}</div></div>
  <div class="card"><div class="k">Exit value</div>
    <div class="v">{fmt_money(returns['exit_value'])}</div></div>
</div>

<h2>Cash flow</h2>
<table>
<tr><th>Year</th><th class="num">Rent PSF</th><th class="num">Occ</th>
<th class="num">EGI</th><th class="num">NOI</th><th class="num">Cash flow</th></tr>
{cash_rows}
</table>

<h2>What moves the answer</h2>
<table>
<tr><th>Assumption</th><th class="num">Range</th>
<th class="num">IRR across range</th><th class="num">Swing</th></tr>
{sens_rows}
</table>

<p class="foot">Assumptions and sourcing: <code>deal.json</code> and
<code>SOURCES.md</code>. Edit the model, then hit re-run.
Illustrative only — not investment advice.</p>

<p class="brand">Built at Claude Code for Real Estate ·
<a href="https://lauriesartain.com/claude">lauriesartain.com/claude</a></p>
</div></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            page = render_page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
        except Exception as e:
            msg = (f"<h1>Model error</h1><pre>{html.escape(str(e))}</pre>"
                   f"<p>Fix the error (or ask Claude Code to), "
                   f"then refresh this page.</p>").encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, *args):
        pass  # keep the terminal quiet


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    if port_in_use(PORT):
        print(f"A dashboard is already running at http://localhost:{PORT}")
        print("Opening it in your browser. (To restart fresh: close the other")
        print("terminal running dashboard.py, or press Ctrl+C there first.)")
        webbrowser.open(f"http://localhost:{PORT}")
        return

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"Dashboard running at {url}")
    print("Press Ctrl+C to stop.")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
