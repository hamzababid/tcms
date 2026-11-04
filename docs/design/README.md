# UI design reference

High-fidelity screens for TCMS. They implement `docs/07-UI-UX-Specification.md`; the live, editable canvas is the "TCMS UI Design" artifact.

Each `*.dc.html` file is one screen written as HTML with inline styles (a design-tool format: `{{…}}` holes are filled by the small script at the bottom of each file). Use them as **visual and structural reference**, not as code to copy: rebuild them with the React + Tailwind + shadcn/ui components from `docs/04-LLD.md §11.4`.

| File | Screen | Spec |
| --- | --- | --- |
| Main.dc.html | Foundations: colour, type, status badges, buttons, fields, table anatomy | 07 §6 |
| Sidebar.dc.html, Topbar.dc.html | App shell components | 07 §3 |
| Dashboard.dc.html | Project overview / QA Manager dashboard | 07 §5.3, §5.12 |
| Repository.dc.html | Folder tree, case list, bulk bar, case side panel | 07 §5.4, §5.6 |
| CaseEditor.dc.html | Test case editor with step grid | 07 §5.5 |
| CycleDetail.dc.html | Cycle progress and runs table | 07 §5.8 |
| Runner.dc.html | Execution runner (interactive; live BR-09 roll-up preview) | 07 §5.9, 02 §7.3 |
| Defect.dc.html | Defect detail with history and links | 07 §5.10 |
| Traceability.dc.html | Requirements traceability matrix | 07 §5.11 |
| Readiness.dc.html | Release readiness and go/no-go decision | 07 §5.15 |
| Login.dc.html | Sign in and MFA | 07 §5.1 |

## Tokens to carry into `frontend/src/styles/tokens.css`

| Token | Value |
| --- | --- |
| Font UI / mono | Inter / JetBrains Mono |
| Ink / secondary / muted | #0F172A / #475569 / #64748B |
| Border / ground / surface | #E2E8F0 / #F8FAFC / #FFFFFF |
| Accent / hover / tint | #4F46E5 / #4338CA / #EEF2FF |
| Sidebar bg / active | #111827 / #312E81 |
| Radius control / card | 6 px / 8 px |
| Row / header height | 40 px / 36 px |

Status (text · background · border · bar): passed #166534 · #DCFCE7 · #BBF7D0 · #16A34A — failed #B91C1C · #FEE2E2 · #FECACA · #DC2626 — blocked #92400E · #FEF3C7 · #FDE68A · #D97706 — skipped #475569 · #F1F5F9 · #E2E8F0 · #94A3B8 — in progress #075985 · #E0F2FE · #BAE6FD · #0284C7 — not run #475569 · #FFFFFF · #CBD5E1 — N/A #556070 · #F8FAFC · #E2E8F0 — needs retest #5B21B6 · #EDE9FE · #DDD6FE · #7C3AED.

Sample data in the screens (names, counts, keys) is illustrative.
