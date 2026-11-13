# EnAbleton MVP product requirements

**Status:** kickoff draft; owner decisions are listed in [DECISIONS.md](DECISIONS.md).

**Authority:** the supplied public Gumroad launch MVP checklist.

**Product shape recommendation:** technical MCP tool for the first MVP, based on the current codebase. This is a recommendation, not an approved product decision.

## Product summary

EnAbleton is currently a local Python MCP extension and generated Ableton Live
Remote Script. The MVP should make it safe and understandable for a producer to
install that tool, connect a supported MCP client, confirm the Live bridge, and
complete a small number of reliable production workflows with evidence and a
recoverable project. The MVP is not a new general-purpose DAW interface.

**Target users:** independent music producers who use Ableton Live and want to
use an MCP-capable desktop assistant for bounded production tasks; technically
comfortable early adopters willing to follow setup instructions and report
reproducible issues.

**Problem:** the current installation requires command-line setup, a manually
provided User Library path, a Live restart and a Control Surface selection.
Users also need to assemble MCP client configuration and distinguish a healthy
connection from a compatible, actually loaded Remote Script. This creates
avoidable setup risk and makes it hard to trust powerful Live-editing tools.

**Value proposition:** one clearly guided local setup, explicit compatibility
and health diagnostics, and three repeatable production workflows that preview
or verify changes and preserve originals. Do not promise that every Live action,
plug-in control or musical result is available or automatically correct.

## Goals and non-goals

### MVP goals

- Complete the supplied ten launch milestones, with a specific release gate for
  each in [the roadmap](ROADMAP.md).
- Make setup state, selectable port, application/bridge versions, compatibility
  result, backup location and recovery steps understandable to a producer.
- Deliver three named, documented workflows with reproducible before/after
  evidence and an explicit distinction between software tests and real Live
  readback or audition.
- Preserve the user's set and source media during installation and recovery.
- Ship release materials only after legal, support, compatibility and product
  ownership decisions are supplied and reviewed.

### Non-goals for this MVP

- A producer-facing standalone or hosted application. This is a separate
  product-shape decision, not an assumed future deliverable.
- Replacing Ableton Live, controlling its GUI with accessibility automation,
  controlling hidden plug-in parameters, or claiming complete Live API access.
- Automatic project migration or edits during installation.
- Unreviewed claims of compatibility with Live versions, operating systems,
  editions or MCP clients.
- Inventing legal terms, privacy promises, support contact details, refund terms,
  or a public release date.

## Core user journeys

1. **Install and orient:** producer obtains the supported package, finds or
   confirms the Live User Library, installs the generated Remote Script with a
   backup, sees the exact Control Surface and restart steps, and confirms setup
   without changing the open song.
2. **Configure and diagnose:** producer sees the first-run status, chooses a
   supported non-conflicting port, checks package
   and running-bridge versions, receives a clear incompatibility explanation,
   and can uninstall or restore using documented steps.
3. **Connect a client:** producer selects Claude Desktop or Cursor, gets a
   generated configuration for the actual checkout/install location, applies
   it, reconnects the client and confirms an MCP connection.
4. **Inspect and repair:** producer inspects a target, previews a bounded
   repair, reviews the target identity and expected change, applies only when
   safe, then verifies readback and original preservation.
5. **Edit an arrangement:** producer selects an arrangement task, previews
   changes, applies the approved edit, and compares a recorded before/after
   state without claiming an audible improvement unless it was auditioned.
6. **Work on sound/devices:** producer inspects an exposed device/parameter,
   previews or applies a supported change, verifies actual parameter readback,
   and sees explicit limits for unavailable controls.
7. **Recover or leave:** producer finds the backup location, follows a
   documented restore path, or uninstalls the Remote Script without deleting
   the Live set, source media or unrelated files.

## Functional requirements

| ID | Requirement |
| --- | --- |
| FR-1 | Bootstrap must discover or let the user confirm the actual User Library, install the Remote Script safely, run a setup check, and clearly explain the Live Control Surface selection and restart step. |
| FR-2 | A first-run/configuration and diagnostics experience must provide port selection and conflict detection, show package and running-script versions and setup status, and provide uninstall and recovery guidance. If port selection cannot be supported safely, the scope must be explicitly re-approved before release rather than silently reduced to a fixed port. |
| FR-3 | MCP client setup must generate usable configuration for Claude Desktop and Cursor, using the user's actual installation path and clear reconnect instructions. |
| FR-4 | Ship three reliable, producer-oriented workflows: inspect/repair, arrangement editing, and sound/device work. Each must define a bounded scenario, prerequisites, preview/approval, failure behavior, verification and evidence. |
| FR-5 | Before a Live-editing workflow, provide a user-confirmed safe save/copy path for the project, record the copy/backup location, and never silently overwrite the original. Installation and bootstrap must never edit the user's song. Every write workflow must identify its target and provide appropriate preservation/recovery behavior. |
| FR-6 | Release materials must include README, quick start, troubleshooting, changelog, EULA, privacy policy, refund policy and support email/contact. Existing files may be revised, but missing policies/contact information require owner input. |
| FR-7 | A compatibility gate must reject unsupported Live versions/configurations before setup or writes, explain the detected and supported versions, and provide recovery/upgrade guidance. |
| FR-8 | Produce a demo video showing a real producer workflow. It is an external production deliverable; this repository provides an evidence script/checklist, not the video itself. |
| FR-9 | Clean release contents and keep the product version consistent between `pyproject.toml` and the generated Remote Script; separately identify upstream and bridge-protocol versions. |
| FR-10 | Record and resolve the product-shape decision before scope is treated as approved. Recommend the technical MCP tool for this MVP; producer-facing app remains an explicit deferred alternative. |

## Nonfunctional requirements

- **Safety:** installer/setup/uninstall must not modify a Live set or source
  media. Before a Live write, identify the target freshly and refuse stale or
  ambiguous targets. Show failures and partial outcomes rather than presenting
  them as success.
- **Recoverability:** show where backups were written and tested restore steps;
  never overwrite an existing installation or project silently.
- **Compatibility:** fail closed outside the explicitly tested support matrix.
  Unit tests and fake Live objects are not evidence of compatibility or sound.
- **Evidence:** label evidence as automated/fake-Live, actual Live readback, or
  actual audition. Never imply one proves another.
- **Privacy:** document local processing and every exception. Existing catalog
  documentation describes an optional Replicate-backed audio-description tool
  that uploads the selected audio; the privacy policy must address this with
  owner/legal review before launch.
- **Release integrity:** no user sets, credentials, local configuration,
  commercial samples or private reports in source or release artifacts.

## Measurable acceptance criteria

- A first-time tester starting from a clean supported machine completes the
  install, Control Surface activation and client connection using the published
  instructions, with no undocumented manual fix; record the exact environment.
- Installer tests cover fresh install, existing install, locally modified files,
  interrupted/failed install, backup creation, restore and uninstall. No case
  changes a Live set.
- Diagnostics identify installed package version, running bridge version,
  selected port and port-conflict state, and compatibility status;
  unsupported versions are blocked with actionable text before any write.
- Claude Desktop and Cursor configurations are generated from the actual
  location, parse as valid client configuration, and produce a successful
  reconnect on each explicitly supported client version.
- Each of the three workflows has a repeatable test fixture and evidence
  record: initial state, selected target, preview, operation result, readback,
  preservation check and limits. Real-Live checks and auditions are separately
  recorded where required; fake-Live tests are labeled as such.
- The save/copy and restore journey succeeds on the supported test environment;
  backup location and recovery instructions match observed behavior.
- Required release documents and owner-supplied legal/support inputs are
  approved; the release checklist has no unchecked launch blocker.
- Package and generated Remote Script report the same EnAbleton release
  version; upstream and bridge-protocol versions remain separately identified.
- The demo video shows the selected supported environment and one end-to-end
  workflow, including safety/verification, without exposing user data or
  suggesting unsupported functionality.

## Risks and dependencies

- **Product-shape scope:** a producer-facing application would require a
  distinct UX, packaging and support scope. Resolve before promising the
  launch interface.
- **Live API variance:** edition/version/device differences can block features;
  support must be based on a recorded matrix, not package CI.
- **Setup complexity:** generated configs, path discovery and port ownership
  differ by OS/client; define the supported OS and client versions.
- **Data/privacy:** local control does not mean every optional tool is local.
  Review the documented Replicate audio upload and all release telemetry/data
  flows before making privacy claims.
- **Recovery and writes:** set preservation must be demonstrated for the three
  workflows. An installer backup is not a substitute for a user project copy.
- **Owner dependencies:** product-shape approval, supported compatibility
  matrix, legal-policy review, support contact, refund terms, release channel and
  demo-video owner are unresolved; see [DECISIONS.md](DECISIONS.md).
