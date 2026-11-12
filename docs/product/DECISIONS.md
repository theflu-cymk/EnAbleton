# Product decision log and owner inputs

This log separates the recommended project direction from approved decisions.
No owner approval is inferred by these documents.

| ID | Decision or input needed | Current position | Owner / status |
| --- | --- | --- | --- |
| D-1 | First MVP product shape: technical MCP tool or producer-facing app | Recommend technical MCP tool. It matches the current Python package, MCP server, generated Remote Script, installer and docs. A producer-facing app has distinct UX, packaging and support scope and must not be silently included. | Product owner — **open; decide in Phase 0** |
| D-2 | Exact supported Live versions, editions, OS versions and client versions | Existing docs identify Windows Live 12 / Live 12.2.5 Suite as development context, not a complete supported matrix. | Product + engineering — **open; test and approve before compatibility claims** |
| D-3 | Port behavior | Current installation docs state loopback port 9877. Whether a configurable port is safe and supportable is unverified. If it remains fixed, diagnostics and marketing must say so. | Engineering + product — **open** |
| D-4 | Release channel and intended audience | Recommend a consented, one-user beta before public Gumroad availability; beta is not a public launch. | Product owner — **open** |
| D-5 | Legal terms | `LICENSE` is present, but that does not supply an EULA, refund policy or product-specific legal review. Do not draft binding promises from assumptions. | Legal/product owner — **must provide/review** |
| D-6 | Privacy statement and data handling | Confirm local data flows, logs, retention and any optional external processing. Tool catalog describes an optional Replicate audio upload. | Privacy/legal + engineering — **must review before publication** |
| D-7 | Support contact, service level and refund terms | No support email/contact, response commitment or refund terms were found. | Product/support owner — **must supply** |
| D-8 | Workflow owners and proof standard | Three workflows are fixed by the supplied checklist; owners, target scenarios, success thresholds and approved test material remain to be assigned. | Product + engineering — **open** |
| D-9 | Safe copy/save behavior and backup retention | Installer currently documents local backups. Product-level save/copy UX, project backup responsibility and retention policy require definition. | Engineering + product — **open** |
| D-10 | Demo-video producer, location, consent and publication | A real workflow demo is required; no video is included in this repository. Choose owner and only use consented material. | Marketing/product — **open** |
| D-11 | Release version and labeling | Current package and generated bridge expose separate version concerns. Choose the next product version only after scope and release policy are approved; keep package and generated Remote Script product versions consistent. | Release owner — **open for MVP release** |

## Decision protocol

Record each decision with its owner, date, evidence and impact on the PRD or
roadmap. Until D-1 is resolved, the recommended MCP boundary is a planning
assumption only. Until D-2 and D-6 are resolved, do not claim broad
compatibility or make categorical privacy promises. A missing D-5/D-7 input is
a public-launch blocker, not permission to invent policy or contact details.
