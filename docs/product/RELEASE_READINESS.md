# MVP release readiness

Use this as the release owner's evidence checklist. An unchecked blocker means
the release is not ready. Record evidence locations and reviewer/date during
execution; this file is a template and makes no claim that any gate has passed.

## Status at `v0.1.0-beta.2`

| Gate | State |
| --- | --- |
| D-1 product shape approved | Done: technical MCP tool, `DECISIONS.md`. |
| Supported platform stated | Done: Windows, Live 12 or later; enforced by `compat.py`. |
| User Library discovery, install, uninstall, setup check | Done and covered by tests. |
| Unsupported Live rejected before writes | Done and covered by tests. |
| Fixed port with documented override | Done: `ENABLETON_PORT` / `--port`, mismatch reported. |
| Generated Claude Desktop / Cursor entry | Done; not validated against installed client versions. |
| EULA, privacy, no-refund terms, support channel | Written; legal review and a support email remain. |
| Version consistency | Done: `0.1.0b2` in package, lock file, catalog and release notes. |
| Three workflows with real-Live evidence | **Outstanding**, needs a Live host; see `WORKFLOWS.md`. |
| Demo video | **Outstanding**, external deliverable. |
| One-user beta completed | **Outstanding.** |

## Product and scope

- [ ] D-1 product shape is approved; the released experience matches that scope.
- [ ] Target user, supported OS/client versions, beta/public status and release
  channel are stated.
- [ ] All ten supplied launch checklist items are traced to completed,
  reviewed deliverables.
- [ ] One-user beta completed with consent; feedback and blockers dispositioned
  before the public go/no-go.

## Setup, safety and compatibility

- [ ] Clean-machine bootstrap discovers or confirms the actual User Library,
  safely installs the Remote Script, explains Control Surface/restart steps and
  checks the setup result.
- [ ] First-run diagnostics report package and running bridge versions and
  compatibility; unsupported Live versions are rejected before writes with
  actionable recovery guidance.
- [ ] Port selection and conflict handling are tested; a fixed-port deviation
  has explicit product-owner scope approval before release.
- [ ] Claude Desktop and Cursor generated configs use actual user paths and are
  validated against the approved client versions.
- [ ] Fresh install, replacement, modified-install refusal, failure rollback,
  uninstall and documented restore are verified. No Live set is modified.
- [ ] Each of the three workflows has automated coverage, target/preview/
  apply/readback evidence and appropriate original-preservation proof.
- [ ] Fake-Live results, actual Live readback and actual audition are labeled
  separately; no unsupported audible or compatibility claim is made.
- [ ] The user-confirmed project save/copy instructions and backup location are
  verified against actual behavior; recovery is tested and the original is not
  silently overwritten.

## Release materials and external deliverables

- [ ] README and quick start describe the shipped version and tested setup.
- [ ] Troubleshooting and changelog are current; obsolete release drafts are
  clearly superseded or corrected.
- [ ] EULA, privacy policy and refund policy are supplied/reviewed by the
  appropriate owner; none were invented to fill a checklist.
- [ ] Support email/contact is supplied, monitored and present in release
  materials.
- [ ] Real producer workflow demo video is recorded, reviewed and published
  with participant/project consent. This is an external production item; no
  video is created by this checklist.
- [ ] Product version in `pyproject.toml` matches the generated Remote Script;
  upstream package and bridge protocol are separately identified.
- [ ] Repository and distribution contain no credentials, local configuration,
  Live sets, private reports or unlicensed media; package resources and license
  notices are checked.

## Sign-off

| Role | Name | Decision/date | Evidence or blocker |
| --- | --- | --- | --- |
| Product owner |  |  |  |
| Engineering/release owner |  |  |  |
| Support owner |  |  |  |
| Legal/privacy reviewer |  |  |  |
| Go/no-go |  |  |  |
