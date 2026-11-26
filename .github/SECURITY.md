# Security Policy

## Supported versions

| Version        | Supported          |
| -------------- | ------------------ |
| 1.x (main)     | :white_check_mark: |
| < 1.0          | :x:                |

## Reporting a vulnerability

The server is a zero-dependency, read-only stdio process (no network access, no file
writes, no credentials), but we still want to hear about anything that looks wrong.

- **Preferred:** use GitHub's private "Report a vulnerability" form on this repository
  (Security tab -> Advisories -> Report a vulnerability), or
- **Email:** team@ouba.art with the subject `[branching-story-mcp security]`.

Please do not open a public issue for security problems. We acknowledge reports within
3 business days and aim for a fix or a documented decision within 14 days.

## Scope

- JSON-RPC / MCP message handling in `branching_story_mcp/server.py` and `js/server.mjs`
- Input validation of story graphs, transcripts and benchmark filters
- Anything in the Docker image or packaging (`pyproject.toml`, `package.json`, `jsr.json`)
