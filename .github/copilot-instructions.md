# EnAbleton producer-workflow guidance

- Read the repository-root `AGENTS.md` before development work; it is the
  source for project-specific practices and required code-change checks. This
  file supplements it and does not replace or weaken it.
- Before editing, inspect the relevant code/docs/tests and current worktree.
  Preserve unrelated user changes; read and integrate dirty files instead of
  reverting or overwriting them. Keep changes within the assigned scope.
- For multi-step work, make a short plan and track meaningful dependencies.
  Implement the smallest complete change, reuse existing patterns, and update
  directly related documentation. Delegate only independent work that benefits
  from separate context; keep a single continuous investigation together.
- Validate the behavior changed, starting with the smallest meaningful test or
  check. For code changes, run the exact unit, integration, Ruff lint and format
  commands in `AGENTS.md`; run `uv build` and inspect packaged JSON/resources
  when preparing a release. Fix regressions introduced by the change; report
  pre-existing failures separately. Documentation-only edits need no code test.
- Before handoff, inspect the full diff and status, check whitespace, and ensure
  no unrelated files, generated artifacts, secrets, local config, user Sets,
  presets, or commercial media were added. State the outcome, files changed,
  exact checks and results, evidence versus assumptions, capability gaps, and
  unresolved questions. Do not claim checks or behavior that were not verified.
- Avoid destructive commands and broad cleanup. Never edit the user's Live Set
  during installation. Do not operate Ableton, run setup, or use UI automation
  unless the user explicitly requests a supported Live task; respect approvals,
  target guards, preservation, and readback requirements in `AGENTS.md`.
- For Live capabilities, check the tools and schemas exposed in the current MCP
  session first. The generated `docs/TOOL_CATALOG.md`, `docs/ACCESS.md`,
  `docs/LIMITATIONS.md`, `docs/PERFORMANCE.md`, and recipe catalog are references,
  not proof that a tool is available or works in this Live version.
- Label evidence precisely: measured audio, heuristic estimate, synthetic or
  fake-Live test, actual Live readback, and human audition are different things.
  Never describe meters or analysis as having heard the Set.
- Preserve source media, original tracks/clips, recipe provenance and stable
  recipe IDs. Refresh target identity before writes, use supported name/start
  guards, and verify affected objects afterward. After a timeout, inspect state
  before retrying. Do not claim a rollback unless readback confirms it.
- Keep edits scoped to the user's request and obey platform approval gates.
  Never automate Ableton's UI, bypass approvals, or claim access to hidden
  plug-in controls. Explain a capability gap and the manual Live action needed.
