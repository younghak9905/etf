# Agent Instructions

## Work History

- Before starting work, read `docs/history.md` to understand the latest project state, recent decisions, and completed changes.
- After completing work, update `docs/history.md` with a concise entry describing what changed, what was verified, and any important follow-up context.
- Keep history entries factual and brief. Prefer concrete files, commands, endpoints, or test results over broad summaries.
- If work is interrupted or only partially completed, still record the useful state when it helps the next agent continue safely.

## Runtime Environment

- Treat Docker as the default environment for both testing and operations going forward.
- Prefer validating runtime behavior against the Docker-backed stack before treating local non-Docker execution as authoritative.
