# Live-operation performance

## Implemented

The collector batches track metadata, group reads, Arrangement summaries and
independent consistency checks, as well as clip details. Batches contain at most
48 read commands; all Live access stays on Live's main thread. No parallel Live
writes, stale-state cache, disabled guards, or changed permission settings.

`collect_live(connection, track_indices=[2, 3, 4])` captures only those current,
zero-based track positions. It validates their existence, and still rechecks
their identities and Arrangement boundaries. Full-set checks use the default
scope. This optional scope is a Python API, not a new CLI flag or MCP tool.

Snapshots and lint reports expose actual bridge round-trip counts and elapsed
bridge seconds. These exclude shell startup, permission review, audio analysis,
report serialization, and user response time.

Command failures are isolated by splitting read batches. Transport failures and
timeouts do not fan out into per-command retries. Incomplete responses remain
capture errors. The batch helper refuses mutation commands.

## Workflow

- Start small: inspect the named tracks/clips, not the entire set for every edit.
- Capture once per plan. Recheck only affected objects before writing and after.
- Keep full audits for initiation and explicit whole-set requests.
- Reuse prepared audio features when source path, size, timestamp, window and
  relevant Warp mapping are unchanged. Do not re-decode whole stems per note.
- Prepare work and backups before one scoped application operation. Use the
  bridge's native batch for related guarded edits; inspect partial failures.
- Retain instrument/preset selections, original-note backups and readback.
- Report permission-review latency separately. Batch work to avoid unnecessary
  approval round trips; never bypass required permissions or security review.

## Validation

A deterministic 24-track test reduces transport requests from 122 in the old
collector to 6, while preserving all track and note reads and freshness checks.
This measures request count, not a promised wall-clock speedup. A live benchmark
compares the old/full, new/full and new/scoped collector against the same bridge.
Its local JSON report is outside Git because it describes a user's session.

## Measured local Live benchmark

| Capture | Seconds | Bridge requests |
| --- | ---: | ---: |
| old_full | 18.058 | 42 |
| new_full | 2.569 | 6 |
| new_seven_midi | 2.601 | 6 |

Full-capture equivalence: True.
Values exclude permission review and do not guarantee other sets.

## MCP compatibility-check overhead

The custom dispatch path previously checked script capabilities, then entered a
wrapper that checked the same version again before dispatching. It now uses two
bridge calls instead of three: one fresh version/capability check and the actual
command. Unsupported versions or capabilities still block the command. No cache
or weaker write preconditions are introduced. Reconnect the MCP client to load
the launcher change; the Live Remote Script does not need a reload.
