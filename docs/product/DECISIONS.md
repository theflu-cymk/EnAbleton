# Product decision log and owner inputs

Decisions are recorded with the owner's answer and the artifact that carries it.
Where the answer left a detail open, the assumption in use is named here so it
can be corrected rather than discovered later.

| ID | Decision | Answer | Evidence and any open detail |
| --- | --- | --- | --- |
| D-1 | MVP product shape | **Technical MCP tool.** No producer-facing app is in scope. | `PRD.md`, `CURRENT_STATE.md`; the CLI and MCP server are the product. |
| D-2 | Supported Live versions, editions, OS and clients | **Windows only for now, Ableton Live 12 or later.** macOS and Linux are unsupported until someone tests them. Editions and individual 12.x builds remain unverified. | `INSTALLATION.md`, `LIMITATIONS.md`, `README.md`; the floor is enforced in `src/enableton/compat.py`. macOS nil: no support claim to withdraw. |
| D-3 | Port behaviour | **Fixed loopback port 9877, overridable.** `ENABLETON_PORT` (or `--port`) changes it for both sides; the value is baked into the generated script, because Live does not inherit a shell's environment. A mismatch is reported, not retried. | `src/enableton/port.py`, `bridge_builder.py`, `doctor.py`, `tests/unit/test_port.py`, `INSTALLATION.md`. |
| D-4 | Release channel and audience | **Small, consented beta before public sale.** No public launch, no free distribution. | `RELEASE_READINESS.md`; one-user beta gate stays unchecked until it runs. |
| D-5 | Legal terms | **Standard proprietary product licence, no refunds.** EnAbleton's own code is licensed, not sold, under a single-user EULA. Upstream MIT notices are preserved separately. | `LICENSE`, `docs/TERMS.md`, `THIRD_PARTY_NOTICES.md`. **Open detail:** the governing-law line names the purchase page's jurisdiction; a lawyer has not reviewed the text. |
| D-6 | Privacy statement | **Default local-only statement.** No telemetry, no accounts, no background uploads; the one optional audio-question tool uploads only when explicitly invoked. | `docs/PRIVACY.md`. |
| D-7 | Support contact and response time | **Repository issue tracker, response within five business days, no refunds.** | `docs/TERMS.md`, README. **Open detail:** a dedicated support email must be added before public sale; the issue tracker is a licence-holder channel, not a public address. |
| D-8 | Workflow owners and proof standard | **Three fixed workflows with a real-Live evidence bar**, defined in `WORKFLOWS.md`. | `WORKFLOWS.md`. Evidence is outstanding because it needs a Live host. |
| D-9 | Safe copy/save and backup retention | **Never overwrite the open set without asking. Installer and uninstall backups under `~/.enableton/backups`, kept 30 days, pruned by hand.** | `INSTALLATION.md`, `PRIVACY.md`, `installer.py`. Retention is documented policy; pruning is manual, so no code silently deletes a backup. |
| D-10 | Demo video | **Recorded by the owner from the owner's own material, with consent for anything not original, published with the release.** | `WORKFLOWS.md`, `RELEASE_READINESS.md`. External deliverable; no video is in the repository. |
| D-11 | Release version and labelling | **`0.1.0b2` / `v0.1.0-beta.2`** — the second MVP beta, not the v0.2.0 melody-matching roadmap. | `pyproject.toml`, `src/enableton/__init__.py`, `docs/RELEASE-v0.1.0-beta.2.md`, regenerated catalog. |

## What remains open

Nothing in this log is waiting on the owner for a product decision. Three items
still need external input or a machine with Live:

1. D-5: legal review of the licence wording, and the governing-law line.
2. D-7: a monitored support email address for the purchase page.
3. D-8 and D-10: real-Live evidence and the recorded demonstration.

## Recording a change

Add a row or amend the answer, state the evidence path, and note the date. Do
not record an assumption as approval: name it as an assumption until the owner
confirms it.
