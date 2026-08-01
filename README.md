# HighGround — FYP flood-recovery coordination platform

Final-year project: residents submit flood-recovery aid requests; disaster officers verify
and prioritise them with an explainable scoring rubric; NGOs claim cases and run tasks;
admins govern rubric versions and audit. **Development phase: Jul 6 – Oct 15 2026.**

## Start here

| You want… | Go to |
|---|---|
| The working contract (who writes what, fixed decisions) | `CLAUDE.md` |
| Where we left off / what's next | newest entry in `docs/devlog/` |
| The development-phase plan | `docs/superpowers/specs/2026-07-05-development-phase-plan-design.md` |
| Learning checklist + exit gates | `docs/LEARNING.md` |
| Why any decision was made | `docs/adr/` (ADR-001…010), history in `docs/GAPS-AND-ACTIONS.md` |
| The frozen UI design (31 screens) | `design-prototype-v2/` — open `index.html`; rationale in `DESIGN-GUIDE.md` |
| The database contract | `Own report/diagrams-lucidchart/LUCIDCHART-ERD-USECASE-SPEC.md` |
| The report (Ch. 1–3) | `Own report/Merged_Report_…_172928.docx` (newest surviving copy) |

## Folder map

```
CLAUDE.md              auto-loaded working contract for every Claude session
docs/                  plan spec · ADRs · devlog (session state) · LEARNING.md ·
                       evidence/ (phase-end captures) · GAPS-AND-ACTIONS.md
design-prototype-v2/   FROZEN design contract — port HTML→JSX verbatim, never redesign
design-prototype/      v1 backup (untouched milestone; ignore unless comparing)
Own report/            thesis working set: newest report docx, Lucidchart diagram specs,
                       v2 .drawio source, thesis-format PDF · _archive/ = old versions
                       and superseded diagram generations (incl. DIAGRAM_SPECIFICATION.md
                       — do NOT use it; see ADR-005)
Reference material/    design-guideline PDF, peer reports, FYP1 marksheet (report-only rubric)
archive/               generated prototype-screen exports (docx/pdf)
highground/            (created in Phase 1) backend/ Django + frontend/ Vite React
```

Code will live in `highground/` from Phase 1 (walking skeleton) onward.
