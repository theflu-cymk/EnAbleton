# Privacy statement

EnAbleton runs on your computer and edits the Live set that is open there. It
has no account system, no telemetry, no analytics and no crash reporting.

## What stays local

- **Your Live set, audio and MIDI** are read and written through the loopback
  connection to Ableton Live. They are never uploaded by EnAbleton.
- **Logs and reports** are written only to files you name, or to the folder you
  run the command from. EnAbleton does not collect them.
- **Installer backups** are written under `~/.enableton/backups` on your own
  disk. They are kept for 30 days and pruned by hand; nothing sends them
  anywhere.
- **No preferences or usage history** are recorded beyond the files above.

## The one optional upload

The catalog includes one audio-question tool that can ask a remote model about a
local audio file. It uploads a file only when you explicitly invoke that tool
and supply credentials for that service; it is never called as part of
preparation, analysis or any default workflow. When it is used, the file and the
question go to that third-party service under its own privacy terms, and any API
key you set is read from your environment, not stored by EnAbleton.

If you never invoke that tool, no audio leaves your machine.

## Network activity

The only other network use is `uv` resolving Python dependencies at install
time, and `git` fetching the repository. Both are ordinary package and source
downloads under their own terms.

## What EnAbleton does not do

- No accounts, identifiers, advertising or tracking pixels.
- No background uploads, no remote logging, no usage statistics.
- No reading of files outside the paths you point it at.

## Retention and deletion

Uninstalling removes the Remote Script from your User Library and moves it into a
timestamped backup; no Live set is touched. Deleting `~/.enableton/backups`
removes the installer backups. Nothing else is retained, because nothing else is
collected.

## Contact

Privacy questions go to the support channel listed in [TERMS.md](TERMS.md).
