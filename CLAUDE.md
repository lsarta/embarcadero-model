# Instructions for Claude Code

This repo is used in a live workshop. The people prompting you are mostly
new to Claude Code and many are new to terminals. Optimize for their
success, not for elegance.

## Running the model

- `python3 dashboard.py` starts a local dashboard at http://localhost:8642
  and opens it in the browser. This is the preferred way to show results.
- `python3 model.py` prints the same results to the terminal.
- On Windows, `python3` may need to be `python`.
- When asked to "run the model" or "show me the model," start the
  dashboard unless the user asks for terminal output.
- If the dashboard is already running, changes appear on refresh — tell
  the user to click "Re-run model" in the browser rather than restarting
  the server.

## Making changes

- Keep the code stdlib-only. Do not add dependencies, do not pip install,
  do not create a virtualenv. If a request seems to need a library
  (e.g. Excel export), prefer stdlib approaches (csv module) or ask first.
- When adding debt/leverage: keep the unlevered results visible alongside
  the levered ones so the user can compare. Show debt service and DSCR
  by year. Add the loan's assumptions to deal.json following the existing
  value/range/label/basis structure (basis can say "user-specified").
  Define the debt economics consistently:
  - DSCR means NOI divided by debt service for that period.
  - The outstanding loan balance is repaid from sale proceeds at exit;
    levered exit proceeds = net sale proceeds minus the loan balance.
  - Treat a floating index (SOFR etc.) as fixed at the stated rate for
    the full hold unless the user says otherwise.
  - Origination and financing fees are paid at close and increase
    initial equity.
  - Levered IRR is calculated on equity cash flows: initial equity out,
    annual levered cash flow, then levered exit proceeds.
- Preserve the existing structure: assumptions live in deal.json, logic in
  model.py, presentation in dashboard.py. Don't merge these files or
  restructure the repo.
- Update dashboard.py to display anything new you add to the model, so
  the browser view stays complete.
- Keep the footer credit line ("Built at Claude Code for Real Estate ·
  lauriesartain.com/claude") intact in dashboard.py through any edit.
- Explain what you changed in one or two plain sentences after each edit —
  the user is learning what these changes look like.

## When things break

- If the model errors, fix it and briefly say what was wrong.
- If the user seems lost, suggest `git checkout .` to reset all changes
  and start clean. Reassure them nothing is permanent.
- Never force-push, never delete the .git directory, never touch files
  outside this repo.

## Scope

- This is a teaching model of a hypothetical deal. Keep the illustrative
  disclaimer intact in any output you generate. Don't present results as
  investment advice or real valuations of the actual building.
