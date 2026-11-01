# Security

This is a beta tool with powerful control over a local DAW. The bridge listens
on loopback port 9877 by default and has no network authentication. Do not
expose, forward or publish that port. Use trusted local MCP clients.

Do not include tokens, Live sets, samples or local reports in issues. Report
security-sensitive details privately to the repository owner before disclosing
them publicly. Include the EnAbleton/upstream/Live versions and a minimal
synthetic reproduction when possible.

The project does not execute arbitrary Python supplied through MCP. Added
property access is allowlisted; audio parsing is bounded and isolated. These
controls reduce risk but are not a sandbox for arbitrary untrusted media.
Install only reviewed source/dependencies, and save your set before edits.
