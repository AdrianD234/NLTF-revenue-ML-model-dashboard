# Revenue Outlook Browser Verification

Last verified: 2026-06-24 22:43:12 +12:00

Verification target: `http://localhost:8515`

Browser surface: Codex in-app browser fallback against the already-running local
Streamlit process. No new Streamlit process was started for this pass.

## Checks

- App loaded with title `NTLF Revenue Modelling`.
- `Revenue Outlook` navigation was visible and opened successfully.
- No Streamlit exception block was present.
- `NLTF revenue source controls` rendered.
- `Revenue Outlook controls` rendered.
- Required source-pack panels rendered:
  - `Total path chart`
  - `Uncertainty fan`
  - `Component drill-down`
  - `Selected-FY revenue split`
- `Source-pack validation and manifest` expander opened successfully.
- Governance detail tables rendered, including:
  - `Source gap register`
  - `Series role audit`
  - `Loader export manifest`
- `Crown top-up` was changed from `Exclude` to `Include`.
- The expected governed-gap warning rendered:
  `Crown top-up Include is not applied because no governed top-up value rows are present in the source pack.`
- The release-value gap warning rendered:
  `Full MOT/BEFU release-value table is unavailable; release selection is registry-only and unresolved differences are reported.`

## Screenshot

Local screenshot artifact:
`artifacts/screenshots/revenue_outlook_crown_top_up_include_8515.png`

The screenshot directory is intentionally ignored by git under the repository
artifact policy; this tracked note records the browser evidence without changing
that policy.
