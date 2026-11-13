Both patches in this folder are applied by `.github/workflows/apply-staged-changes.yml`
on a push that touches this folder. The workflow then regenerates `uv.lock`,
`docs/TOOL_CATALOG.md` and `docs/tool-catalog.json`, removes this folder and the
workflow, and commits the result to this branch.
