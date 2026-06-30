# Rerun Review

Status: pass with watch items.

Reviewed rerun behaviour:
- Primary Revenue Outlook controls, selected path chart and fan render before lazy audit sections.
- Reconciliation, composition, EV/PHEV audit, PED bridge diagnostics, sensitivity audit and scenario-role audit are gated by `revenue_outlook_lazy_table`.
- Direct primary filters remain browser-tested through the split host-browser policy.

Findings:
- Default reruns avoid the heaviest audit work unless the corresponding detail section is opened.
- Recent loop evidence shows open-state composition formatting is cached separately from stack construction and figure rendering.
- The performance verifier now uses bounded subprocesses so rerun/browser validation cannot hang indefinitely.

