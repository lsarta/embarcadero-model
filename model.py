"""
Two Embarcadero Center
Unlevered asset valuation model.

Run it:      python3 model.py
Assumptions: deal.json

Reads assumptions, builds a 5-year cash flow, prices an exit at a cap rate,
and returns unlevered IRR and equity multiple.

Then it does the part most models leave out: it tells you which assumptions
actually matter. Every input in deal.json declares a value, a plausible
range, and the reasoning behind it. The model re-runs across each range and
ranks the inputs by how much they move the answer.

Scope: annual periods, unlevered, one blended rent PSF.
"""

import copy
import json
from pathlib import Path


# ---------------------------------------------------------------- inputs

def load_deal(path="deal.json"):
    return json.loads(Path(path).read_text())


def val(deal, section, key):
    """Pull an assumption's value. Inputs are dicts with value/range/basis,
    so the model reads the value and the sensitivity code reads the range."""
    return deal[section][key]["value"]


def ranged_inputs(deal):
    """Every input that declared a range, as (section, key, spec)."""
    out = []
    for section, contents in deal.items():
        if not isinstance(contents, dict):
            continue
        for key, spec in contents.items():
            if isinstance(spec, dict) and "range" in spec:
                out.append((section, key, spec))
    return out


# ---------------------------------------------------------------- math

def irr(cash_flows):
    """IRR by bisection. Dependency-free and won't diverge.
    Assumes cash_flows[0] is negative."""
    def npv(rate):
        return sum(cf / (1 + rate) ** t for t, cf in enumerate(cash_flows))

    low, high = -0.99, 10.0
    if npv(low) * npv(high) > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        if npv(mid) > 0:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def occupancy_for_year(year, deal):
    """Straight-line lease-up from current to stabilized occupancy."""
    start = val(deal, "revenue", "occupancy_pct")
    end = val(deal, "revenue", "stabilized_occupancy_pct")
    years = val(deal, "revenue", "months_to_stabilize") / 12
    if year >= years:
        return end
    return start + (end - start) * (year / years)


def build_cash_flows(deal):
    sf = deal["property"]["rentable_sf"]
    hold = val(deal, "acquisition", "hold_years")
    rent0 = val(deal, "revenue", "in_place_rent_psf")
    growth = val(deal, "revenue", "rent_growth_pct")
    opex0 = val(deal, "expenses", "opex_psf")
    opex_growth = val(deal, "expenses", "opex_growth_pct")
    mgmt_pct = val(deal, "expenses", "management_fee_pct_egi")
    reserves_psf = val(deal, "capital", "reserves_psf")

    rows = []
    for year in range(1, hold + 1):
        rent_psf = rent0 * (1 + growth) ** (year - 1)
        occ = occupancy_for_year(year, deal)
        egi = rent_psf * sf * occ
        opex = opex0 * sf * (1 + opex_growth) ** (year - 1)
        mgmt = egi * mgmt_pct
        noi = egi - opex - mgmt
        rows.append({
            "year": year,
            "rent_psf": rent_psf,
            "occupancy": occ,
            "egi": egi,
            "noi": noi,
            "cash_flow": noi - reserves_psf * sf,
        })
    return rows


def exit_value(rows, deal):
    """Exit priced on forward NOI — the income the buyer inherits."""
    forward_noi = rows[-1]["noi"] * (1 + val(deal, "revenue", "rent_growth_pct"))
    gross = forward_noi / val(deal, "exit", "exit_cap_pct")
    return gross * (1 - val(deal, "exit", "cost_of_sale_pct"))


def run(deal):
    basis = val(deal, "acquisition", "purchase_price") * (
        1 + val(deal, "acquisition", "closing_costs_pct"))
    rows = build_cash_flows(deal)
    sale = exit_value(rows, deal)

    flows = [-basis] + [r["cash_flow"] for r in rows]
    flows[-1] += sale

    return rows, {
        "basis": basis,
        "exit_value": sale,
        "irr": irr(flows),
        "equity_multiple": sum(flows[1:]) / basis,
        "going_in_cap": rows[0]["noi"] / basis,
    }


def sensitivity(deal):
    """Re-run the model at each end of each declared range.

    This is the honest version of a sensitivity table: instead of bumping
    everything by an arbitrary 10%, each input moves across the band we
    actually think it could land in. Ranked by how much the IRR moves.
    """
    _, base = run(deal)
    results = []
    for section, key, spec in ranged_inputs(deal):
        lo, hi = spec["range"]
        outcomes = []
        for v in (lo, hi):
            d = copy.deepcopy(deal)
            d[section][key]["value"] = v
            _, r = run(d)
            outcomes.append(r["irr"])
        results.append({
            "label": spec["label"],
            "basis": spec.get("basis", ""),
            "low_input": lo,
            "high_input": hi,
            "low_irr": min(outcomes),
            "high_irr": max(outcomes),
            "swing": abs(outcomes[1] - outcomes[0]),
        })
    results.sort(key=lambda r: r["swing"], reverse=True)
    return base, results


# ---------------------------------------------------------------- output

def money(x):
    return f"${x:,.0f}"


def report(deal, rows, returns):
    p = deal["property"]
    print()
    print("=" * 74)
    print(f"  {p['name']}  |  {p['city']}")
    print(f"  {p['type']} · {p['rentable_sf']:,} SF · "
          f"{val(deal, 'acquisition', 'hold_years')}-year hold")
    print("=" * 74)
    print()
    print(f"  {'Year':<6}{'Rent PSF':>10}{'Occ':>8}{'EGI':>16}{'NOI':>16}{'Cash Flow':>16}")
    print("  " + "-" * 70)
    for r in rows:
        print(f"  {r['year']:<6}{r['rent_psf']:>10.2f}{r['occupancy']:>8.1%}"
              f"{money(r['egi']):>16}{money(r['noi']):>16}{money(r['cash_flow']):>16}")
    print("  " + "-" * 70)
    print(f"  {'Basis (incl. closing)':<34}{money(returns['basis']):>20}")
    print(f"  {'Going-in cap rate':<34}{returns['going_in_cap']:>20.2%}")
    print(f"  {'Exit value (net of sale costs)':<34}{money(returns['exit_value']):>20}")
    print(f"  {'Exit cap rate':<34}{val(deal, 'exit', 'exit_cap_pct'):>20.2%}")
    print("  " + "-" * 70)
    print(f"  {'UNLEVERED IRR':<34}{returns['irr']:>20.2%}")
    print(f"  {'Equity multiple':<34}{returns['equity_multiple']:>19.2f}x")
    print("=" * 74)


def report_sensitivity(base, results):
    print()
    print("  WHAT ACTUALLY DRIVES THIS")
    print(f"  Base case IRR: {base['irr']:.2%}. Each input moved across its declared")
    print("  range in deal.json, holding everything else flat.")
    print()
    print(f"  {'Assumption':<28}{'Range':>22}{'IRR':>17}{'Swing':>7}")
    print("  " + "-" * 70)

    widest = results[0]["swing"]
    for r in results:
        lo, hi = r["low_input"], r["high_input"]
        if hi <= 1.0:
            rng = f"{lo:.2%} – {hi:.2%}"
        elif hi < 1000:
            rng = f"{lo:,.2f} – {hi:,.2f}"
        else:
            rng = f"${lo/1e6:,.0f}M – ${hi/1e6:,.0f}M"
        irr_rng = f"{r['low_irr']:.2%} – {r['high_irr']:.2%}"
        bar = "█" * max(1, round(r["swing"] / widest * 18))
        print(f"  {r['label']:<28}{rng:>22}{irr_rng:>17}{r['swing']:>7.2%}")
        print(f"  {'':<28}{bar}")
    print("  " + "-" * 70)
    print()
    print("  Read it top down. The assumptions at the top are the ones worth")
    print("  arguing about. The ones at the bottom you can leave alone.")
    print()
    print("  Every range above is a judgment call. They're in deal.json with")
    print("  the reasoning attached — disagree with one and change it.")
    print()


def report_basis(deal):
    print("  WHERE THE ASSUMPTIONS COME FROM")
    print("  " + "-" * 70)
    for section, key, spec in ranged_inputs(deal):
        print(f"  {spec['label']}")
        print(f"      {spec['basis']}")
    print("  " + "-" * 70)
    print()
    print("  Illustrative assumptions for a real building. Not its real numbers,")
    print("  not investment advice.")
    print()


if __name__ == "__main__":
    deal = load_deal()
    rows, returns = run(deal)
    report(deal, rows, returns)

    base, results = sensitivity(deal)
    report_sensitivity(base, results)
    report_basis(deal)
