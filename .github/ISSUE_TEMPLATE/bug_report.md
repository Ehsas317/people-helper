---
name: Bug report
about: Report a bug or unexpected behavior in People Helper
title: "[Bug] "
labels: bug
assignees: ''
---

## Describe the bug

A clear and concise description of what the bug is.

## To reproduce

The exact command you ran:

```bash
people-helper --repo OWNER/REPO --output report.md
```

Any flags that matter (`--no-network`, `--extract`, `--language`, `--debug`, etc.).

## Expected behavior

What you expected to happen.

## Actual behavior

What actually happened — paste the full output (with `--debug` if possible).

## Environment

- People Helper version: (`people-helper --version`)
- Python version: (`python --version`)
- OS: (e.g. Ubuntu 24.04, macOS 15, Windows 11)
- PAT type: (classic / fine-grained)
- Flags used: (e.g. `--no-network`, `--language Python`, `--extract ./out/`)

## Repo being analyzed (optional)

If you can share the `OWNER/REPO` you were analyzing, paste it. If not, a minimal
reproducer or a description of the file that triggered the bug is fine.

## Anything else?

Stack traces (with `--debug`), relevant report excerpts, screenshots — anything
that helps reproduce the issue.
