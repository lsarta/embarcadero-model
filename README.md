# Two Embarcadero Center — Asset Valuation Model

An unlevered DCF for a single office asset. Small, complete, and transparent about its own assumptions — every input declares a value, a plausible range, and where it came from.

Starting point for the Claude Code for Real Estate workshop.

## Requirements

Python 3. No packages, no virtual environment.

## Run it

```bash
git clone https://github.com/lsarta/embarcadero-model.git
cd embarcadero-model
python3 model.py
```

## Files

```
deal.json     Assumptions — value, range, and basis for every input
SOURCES.md    Where the assumptions come from: what's cited, what's derived, what's judgment
model.py      The model
```

## What it does

Builds a 5-year cash flow with rent growth, opex growth, and lease-up to stabilized occupancy. Prices an exit on forward NOI at a cap rate. Returns unlevered IRR and equity multiple.

| Basis (incl. closing) | $395,850,000 |
|---|---|
| Going-in cap | 6.75% |
| Exit value | $527,053,284 |
| Unlevered IRR | 12.62% |
| Equity multiple | 1.71x |

Then it does the part most models leave out: it re-runs across each assumption's declared range and ranks them by how much they move the IRR.

```
  Assumption                        Range              IRR    Swing
  Annual rent growth        0.00% – 4.00%   7.73% – 14.19%    6.46%
  In-place rent ($/SF)      64.00 – 74.00  10.04% – 16.18%    6.14%
  Purchase price            $355M – $425M  10.46% – 15.04%    4.58%
  Exit cap rate             5.75% – 7.00%  10.54% – 14.19%    3.66%
  Operating expenses ($/SF) 22.00 – 27.00  10.86% – 14.30%    3.44%
  Stabilized occupancy    88.00% – 95.00%  10.78% – 13.93%    3.15%
  Annual opex growth        2.00% – 3.50%  12.05% – 12.89%    0.85%
  Months to stabilize       12.00 – 36.00  12.52% – 12.72%    0.20%
```

Rent growth ranks first because its range honestly includes zero — asking rents grew 3.7% year-over-year by one measure (CBRE) and have been flat for six quarters by another (Newmark). When credible sources disagree, the band widens, and wide bands are what move valuations. Every range is declared in `deal.json` with its reasoning, and `SOURCES.md` has the full citations. Disagree with a band and change it — the ranking will move.

## Scope

Annual periods. Unlevered. One blended rent PSF rather than a lease-level rent roll.

## The deal is hypothetical

Two Embarcadero Center is a real building, owned by BXP, and not for sale. The building facts (size, occupancy) are real and cited in `SOURCES.md`. The deal terms and financial assumptions are our judgment calibrated to published 2026 market data — they are not the building's actual economics. Nothing here is investment advice or a valuation opinion.

---

Laurie Sartain · Claude Ambassador for Real Estate
