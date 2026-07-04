# 09 — Skills & modes (use these)

Claude Code skills/modes installed on this project. Any agent working here: use
the right one for the job. Trigger a skill by typing `/<name>`. Modes are always-on.

## Always-on modes
| Mode | Effect |
|------|--------|
| Ponytail | Lazy-senior discipline. Shortest working diff, no over-building, bug fix = root cause not symptom. Runs every response. Off: "stop ponytail". |
| Caveman | Terse output, ~75% fewer tokens, full technical accuracy. Off: "stop caveman". |

## UI / UX
| Skill | Use for |
|-------|---------|
| frontend-design | EVERY page/component. Production-grade, distinctive, anti-AI-slop. Bold aesthetic, real typography, motion, layout. |
| theme-factory | Consistent theme (colors/fonts) across the app. 10 presets or custom. |
| brand-guidelines | Lock brand colors/type. |
| web-artifacts-builder | Complex multi-component UI: React + Tailwind + shadcn/ui, state, routing. |
| canvas-design / algorithmic-art | Static art, posters, generative visuals. |

## Coding quality
| Skill | Use for |
|-------|---------|
| /code-review | Bug + reuse/simplify audit on current diff. `ultra` = cloud multi-agent deep review. |
| /simplify | Cleanup pass (reuse, efficiency); applies fixes. Quality only, not bug hunt. |
| /security-review | Security audit of branch changes. MANDATORY before push — trading = money path. |
| /verify + /run | Prove a change works in the real app, not just tests. |
| /init | Generate CLAUDE.md codebase doc. |

## Context-saving subagents (cavecrew)
Big codebase — use these; output is compressed so main context lasts longer.
| Agent | Use for |
|-------|---------|
| cavecrew-investigator | Locate code: "where is X", "what calls Y", file:line map. Read-only. |
| cavecrew-builder | Bounded 1-2 file edit (typo, single-fn rewrite, rename). |
| cavecrew-reviewer | Diff/branch review, one line per finding. |

## Commit / review helpers
| Skill | Use for |
|-------|---------|
| /caveman-commit | Conventional-commit message, terse. |
| /caveman-review | One-line-per-finding PR review. |
| /caveman-compress | Compress a memory/doc file to save tokens. |

## Recommended workflow for THIS project
1. Build UI → `frontend-design` + `theme-factory`.
2. Write code → Ponytail on. Locate first via `cavecrew-investigator`.
3. Before commit → `/code-review`, then `/security-review` (money path).
4. Confirm → `/verify` or `/run`.
5. Commit → `/caveman-commit`. Push. Log in `08_PROGRESS_LOG.md`.

## Not installed (add if needed)
- mcp-builder — build MCP servers.
- skill-creator — make new skills.
