# MVP roadmap and gates

The supplied checklist is authoritative. This sequence adds dependencies and
exit gates; it does not change the requested scope. Do not set dates until
owners, supported environments and legal inputs are assigned.

| Phase | Deliverable and checklist coverage | Dependencies | Exit gate |
| --- | --- | --- | --- |
| 0. Product boundary | Resolve checklist item 10: approve technical MCP tool for first MVP or explicitly change direction. Confirm target user, operating-system scope, supported client versions, release owner and public/private launch intent. | Product owner decision. | Signed scope in the decision log; no producer-facing app work is implied by approval of the MCP MVP. |
| 1. Setup foundation | Checklist items 1–3 and 7: bootstrap/User Library discovery, Remote Script install, setup check, Control Surface instructions; first-run/configuration, selectable port with conflict/version diagnostics and uninstall; generated Claude Desktop/Cursor configs; pre-write compatibility rejection. | Phase 0; exact supported Live/OS/client matrix; installer and bridge behavior; UX/packaging choice. | Clean-machine test completes install → Live activation → compatible MCP connection and uninstall/restore. Port selection and conflict handling are verified. Unsupported versions fail before writes with clear recovery guidance. No Live set is modified. |
| 2. Workflow proof | Checklist item 4: define and validate inspect/repair, arrangement editing, and sound/device workflows, with before/after evidence. | Phase 1; workflow owners; safe target selection, preview, preservation and readback strategy. | Each workflow passes deterministic tests and recorded supported-host checks. Evidence distinguishes fake-Live tests, Live readback and audition; unsupported operations fail visibly. |
| 3. Preservation and support | Checklist item 5: safe save/copy, documented backup location, restore/uninstall instructions, troubleshooting and support path. | Installer/backup behavior from Phase 1; owner supplies contact and support policy. | Fresh install, update, failure recovery, restore and uninstall verified on the supported environment; docs match observed paths and behavior. |
| 4. Launch materials | Checklist items 6, 8 and 9: README, quick start, troubleshooting, changelog, EULA, privacy, refund, support email; real-workflow demo video; clean repository and consistent product version. | Phases 1–3; legal/policy review; support owner/contact; release asset and video owner. | All required materials are present and approved; demo evidence is reviewed; source and generated Remote Script versions match; release assets are source-only and scanned. |
| 5. Private one-user beta | Exercise the end-to-end experience with one consenting producer before public availability. Use the same support, compatibility and data-handling constraints intended for launch. | Phases 1–4 complete for a narrowly stated beta environment; owner approval and participant consent. | Participant completes setup and all three workflows; failures, recovery, evidence and feedback are recorded; no unresolved safety/data blocker remains. Beta status and limitations are explicit. |
| 6. Public launch gate | Public release only after all ten checklist items, legal/policy approval, tested compatibility claims, support coverage and beta blockers are closed. | Phase 5; owner go/no-go. | Release checklist signed by product, engineering, support and legal/policy owners. Publish only tested compatibility claims and actual demo evidence. |

## Checklist traceability

1. Installer/bootstrap discovers User Library, installs Remote Script, runs setup
   check, explains Control Surface step — Phase 1.
2. Config/diagnostics with first-run screen, port selection, version detection,
   uninstall — Phase 1. If port selection cannot be supported safely, record
   and re-approve the change in scope before launch; do not treat a fixed port
   as satisfying this milestone.
3. MCP client setup for Claude Desktop and Cursor with generated config — Phase 1.
4. Three reliable workflows and before/after evidence: inspect/repair,
   arrangement editing, sound/device work — Phase 2.
5. User-confirmed safe project save/copy flow and documented backup location —
   Phase 3.
6. Release docs/materials: README, quick start, troubleshooting, changelog, EULA,
   privacy policy, refund policy, support email — Phase 4.
7. Compatibility gate rejects unsupported Live versions clearly — Phase 1.
8. Demo video of real producer workflow — Phase 4; external production
   deliverable, not completed by these repository documents.
9. Clean repository and consistent product version in `pyproject.toml` and
   Remote Script — Phase 4.
10. Early product-shape decision: technical MCP tool versus producer-facing app
    (distinct scope; codebase today is technical MCP tool) — Phase 0.

## Evidence and gate rules

- Record Live version/edition, OS, MCP client/version, bridge protocol and device
  availability for each manual run. A tested configuration is not a universal
  compatibility promise.
- Capture before/after state from the target workflow; use synthetic or
  owner-approved project material. Keep private user sets, logs and reports out
  of source and release artifacts.
- Unit/integration tests, generated-script checks, Live readback and audition
  are separate evidence types. A workflow cannot claim audible success from
  fake-Live tests or state diffs alone.
- One-user beta is a gated, consented test and is not public launch. Public
  launch requires every required asset, owner decision and go/no-go signoff.
