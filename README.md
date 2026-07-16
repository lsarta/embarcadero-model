# Embarcadero Center — Asset Valuation Model

A deliberately incomplete CRE valuation model, built for the **Claude Code for Real Estate** workshop.

It works. It's also missing most of what a real model needs. That's the point — you're going to add the missing parts yourself, today, by asking for them.

---

## Why we're doing this

Every firm in this room is deciding how to bring AI into its workflow. That decision is always some version of **build or buy**.

You can't make that call well if you've never built anything. You end up taking a vendor's word for what's hard, what's easy, and what's worth paying for.

So today you're going to build. Not because you should become a developer — because after this you'll know roughly what "we'd need to build that" actually costs. That's the skill. It transfers to every vendor conversation you have for the rest of your career.

---

## Setup

**You need:** the Claude desktop app, and Python.

Python is already on every Mac. On Windows, if `python3 --version` doesn't work, grab it from [python.org](https://python.org) — or just ask Claude to sort it out.

**Get the code.** In the Claude desktop app, open Claude Code and ask:

> Clone https://github.com/lsarta/embarcadero-model to my desktop, then run model.py and show me the output.

That's it. If something's missing, Claude will tell you what and fix it.

**Or do it yourself:**

```bash
git clone https://github.com/lsarta/embarcadero-model.git
cd embarcadero-model
python3 model.py
```

No dependencies. No install. No virtual environment. Standard library only, on purpose.

---

## What's here

```
deal.json    All the assumptions. Plain numbers, no code.
model.py     The model. ~150 lines, commented.
README.md    This.
```

**Try this first.** Open `deal.json`, change `exit_cap_pct` from `0.0625` to `0.0700`, save, and run `python3 model.py` again.

Watch the IRR move. You just did a sensitivity analysis by hand. In about twenty minutes you'll have the model do it for you.

---

## What it does

Reads assumptions → builds a 5-year cash flow → grows rent, grows opex, leases up to stabilized occupancy → calculates NOI → prices an exit at a cap rate → returns unlevered IRR and equity multiple.

Current output, as shipped:

| | |
|---|---|
| Basis (incl. closing) | $380,625,000 |
| Going-in cap | 6.80% |
| Exit value | $501,001,221 |
| Unlevered IRR | **12.36%** |
| Equity multiple | **1.69x** |

---

## What it doesn't do

This is your menu. Everything below is missing, and everything below is one prompt away.

- **No debt.** Unlevered only. No loan, no interest, no amortization, no levered IRR. *(Start here — it's the biggest gap and the most familiar.)*
- **No sensitivity table.** One exit cap, one answer. No grid across cap rate and rent growth.
- **No TI/LC.** Leasing costs real money. This model pretends it's free.
- **No rent roll.** One blended rent PSF. No individual leases, no expirations, no rollover risk.
- **No waterfall.** No LP/GP split, no pref, no promote.
- **Annual periods only.** No monthly granularity.
- **No export.** Prints to your terminal and forgets. No Excel, no CSV, no chart.
- **No downside case.** No recession scenario, no re-tenanting drag.

Pick one. Ask for it. See what happens.

---

## How to ask

Vague prompts get vague models. The people who get the most out of this hour will be the ones who specify like they're briefing an analyst.

**Weak:**
> add debt

**Strong:**
> Add debt to this model. $240M loan at 65% LTC, SOFR + 250 with SOFR at 4.10%, interest-only for the full term, 1.0% origination fee paid at close. Add a levered IRR and equity multiple to the output, and show annual debt service and DSCR in the cash flow table. Keep the unlevered numbers visible so I can compare.

You already know how to do this. It's the same thing you do when you scope work for a junior analyst — say what you want, say what "done" looks like, say what not to break.

That's the whole skill. The terminal is incidental.

---

## The assumptions are fake

Embarcadero Center is a real building. These numbers are not its numbers. Everything in `deal.json` is fabricated for teaching — plausible, internally consistent, and entirely made up.

Nothing here is investment advice, a valuation opinion, or a representation about any actual asset or transaction.

---

## After today

Everything you build is yours. It's your clone, your repo, your model.

The gap between *"I did this once in a workshop"* and *"my team does this by default"* is real, and it's mostly not a technical gap. If that's the problem you're trying to solve, come find me.

*Laurie Sartain · Claude Ambassador for Real Estate*
