"""
Embarcadero Center — Tower 2
Unlevered asset valuation model.

Run it:      python3 model.py
Assumptions: deal.json

WHAT THIS DOES
  - Builds a 5-year cash flow from the assumptions in deal.json
  - Grows rent, grows opex, lets occupancy lease up to stabilized
  - Calculates NOI, exit value at a cap rate, and unlevered IRR

WHAT THIS DOES NOT DO  <-- this is the interesting part
  - No debt. No loan, no interest, no amortization, no levered returns.
  - No sensitivity analysis. One exit cap, one answer.
  - No TI/LC. Leasing costs money; this model pretends otherwise.
  - No rent roll. One blended rent PSF, no individual leases, no rollover.
  - No waterfall. No LP/GP split, no promote, no preferred return.
  - No monthly periods. Annual only.
  - No export. Prints to terminal and forgets.

Every one of those is a feature you could add today.
"""

import json
from pathlib import Path


def load_deal(path="deal.json"):
    """Read assumptions. Keeping inputs out of code so you can change a
    number without reading Python."""
    return json.loads(Path(path).read_text())


def irr(cash_flows, guess=0.10):
    """Internal rate of return via bisection.

    Deliberately simple and dependency-free. Not as fast as Newton-Raphson,
    but it won't diverge on you, and it needs no numpy.
    Assumes cash_flows[0] is negative (you paid for the thing).
    """
    def npv(rate):
        return sum(cf / (1 + rate) ** t for t, cf in enumerate(cash_flows))

    low, high = -0.99, 10.0
    if npv(low) * npv(high) > 0:
        return None  # no sign change; IRR undefined

    for _ in range(200):
        mid = (low + high) / 2
        if npv(mid) > 0:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def occupancy_for_year(year, deal):
    """Straight-line lease-up from current occupancy to stabilized."""
    r = deal["revenue"]
    start = r["occupancy_pct"]
    end = r["stabilized_occupancy_pct"]
    years_to_stabilize = r["months_to_stabilize"] / 12

    if year >= years_to_stabilize:
        return end
    return start + (end - start) * (year / years_to_stabilize)


def build_cash_flows(deal):
    """Year-by-year operating cash flow. Returns a list of dicts."""
    sf = deal["property"]["rentable_sf"]
    rev = deal["revenue"]
    exp = deal["expenses"]
    cap = deal["capital"]
    hold = deal["acquisition"]["hold_years"]

    rows = []
    for year in range(1, hold + 1):
        # Rent grows from in-place, compounding annually
        rent_psf = rev["in_place_rent_psf"] * (1 + rev["rent_growth_pct"]) ** (year - 1)
        occ = occupancy_for_year(year, deal)

        gpr = rent_psf * sf                    # gross potential rent
        egi = gpr * occ                        # effective gross income
        opex = exp["opex_psf"] * sf * (1 + exp["opex_growth_pct"]) ** (year - 1)
        mgmt = egi * exp["management_fee_pct_egi"]
        noi = egi - opex - mgmt
        reserves = cap["reserves_psf"] * sf
        cf = noi - reserves

        rows.append({
            "year": year,
            "rent_psf": rent_psf,
            "occupancy": occ,
            "egi": egi,
            "opex": opex + mgmt,
            "noi": noi,
            "cash_flow": cf,
        })
    return rows


def exit_value(rows, deal):
    """Sale price = final-year forward NOI / exit cap, net of sale costs.

    Note the convention: exit is priced on the NOI the *buyer* inherits,
    so we grow the last year's NOI forward one period.
    """
    ex = deal["exit"]
    last_noi = rows[-1]["noi"]
    forward_noi = last_noi * (1 + deal["revenue"]["rent_growth_pct"])
    gross = forward_noi / ex["exit_cap_pct"]
    return gross * (1 - ex["cost_of_sale_pct"])


def run(deal):
    acq = deal["acquisition"]
    basis = acq["purchase_price"] * (1 + acq["closing_costs_pct"])

    rows = build_cash_flows(deal)
    sale = exit_value(rows, deal)

    # Unlevered cash flow stream: buy at t0, operate, sell in final year
    flows = [-basis] + [r["cash_flow"] for r in rows]
    flows[-1] += sale

    returns = {
        "basis": basis,
        "exit_value": sale,
        "irr": irr(flows),
        "equity_multiple": sum(f for f in flows[1:]) / basis,
        "going_in_cap": rows[0]["noi"] / basis,
    }
    return rows, returns


def money(x):
    return f"${x:,.0f}"


def report(deal, rows, returns):
    p = deal["property"]
    print()
    print("=" * 72)
    print(f"  {p['name']}  |  {p['city']}")
    print(f"  {p['type']} · {p['rentable_sf']:,} SF · {deal['acquisition']['hold_years']}-year hold")
    print("=" * 72)
    print()
    print(f"  {'Year':<6}{'Rent PSF':>10}{'Occ':>8}{'EGI':>16}{'NOI':>16}{'Cash Flow':>16}")
    print("  " + "-" * 68)
    for r in rows:
        print(f"  {r['year']:<6}{r['rent_psf']:>10.2f}{r['occupancy']:>8.1%}"
              f"{money(r['egi']):>16}{money(r['noi']):>16}{money(r['cash_flow']):>16}")
    print()
    print("  " + "-" * 68)
    print(f"  {'Basis (incl. closing)':<32}{money(returns['basis']):>20}")
    print(f"  {'Going-in cap rate':<32}{returns['going_in_cap']:>20.2%}")
    print(f"  {'Exit value (net of sale costs)':<32}{money(returns['exit_value']):>20}")
    print(f"  {'Exit cap rate':<32}{deal['exit']['exit_cap_pct']:>20.2%}")
    print("  " + "-" * 68)
    irr_str = f"{returns['irr']:.2%}" if returns["irr"] is not None else "n/a"
    print(f"  {'UNLEVERED IRR':<32}{irr_str:>20}")
    print(f"  {'Equity multiple':<32}{returns['equity_multiple']:>20.2f}x")
    print("=" * 72)
    print()
    print("  Illustrative assumptions. Not investment advice.")
    print("  Change a number in deal.json and run this again.")
    print()


if __name__ == "__main__":
    deal = load_deal()
    rows, returns = run(deal)
    report(deal, rows, returns)
