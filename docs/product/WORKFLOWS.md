# The three MVP workflows and their proof standard

These are the workflows the beta is judged on. Each one is a sequence of existing
commands, and each is only "passing" when it has been run in a real Ableton Live
session and the evidence below exists. Simulated tests are necessary but are not
the evidence.

## Workflow 1 — Start a set from scratch

**Request a producer would make:** "I have a rough loop and want a working
arrangement scaffold."

1. Open a new set with at least one audio or MIDI idea.
2. `enableton` (no arguments) and choose `all`, or run the nine steps in order.
3. Review the printed result: what changed, what was skipped, what was
   unsupported.

**Pass evidence:** a screen recording or screenshots of the before and after
track list, the nine-step JSON result, and one Undo returning the set to its
prior state. Originals preserved as muted copies where `adopt` ran.

## Workflow 2 — Prepare an existing rough set

**Request:** "This set is a mess: unnamed tracks, unlabelled clips, full-scale
audio, no locators."

1. `enableton setup` and `enableton doctor` first, and paste their JSON.
2. `enableton` → `all`, with `--plan` reviewed first if the set matters.
3. Read the report of unchanged and unsupported items.

**Pass evidence:** the doctor JSON, the plan output, the applied output, and a
readback of at least three changed fields. No original track, clip or audio file
replaced or overwritten.

## Workflow 3 — Repair and align recorded audio

**Request:** "These stems drift, some clips clip, and the drums are on the wrong
warp mode."

1. Identify the reference track (the longest audio track, or `--reference NAME`).
2. Run `level` (clip gain and DC), then `lock` (warp mode per role), then
   `frame` (bar-aligned loop bounds).
3. Inspect anything reported as unsupported: clicks, gaps and level jumps are
   reported, not silently fixed.

**Pass evidence:** before and after warp modes and clip gain values, the
unsupported list, and a listening note on whether the aligned result actually
sits in time. A timing measurement alone does not pass this workflow.

## What does not count as evidence

- Unit tests over fake Live objects.
- A protocol or transport test.
- A generated plan with no apply.
- A screenshot of code or logs instead of a Live session.
- Any result the producer has not listened to.

## Recording the result

For each workflow, record: date, Windows version, Ableton Live build, EnAbleton
version, bridge protocol, the JSON outputs with secrets removed, and the honest
verdict — improved, unchanged, worse, or insufficient evidence. Store the
material outside the repository unless it is synthetic, and link it from the
release notes.
