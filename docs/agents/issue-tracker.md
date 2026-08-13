# Issue tracker: GitHub

Issues and specs for this repository live as GitHub issues. Use the `gh` CLI for all operations.

The `origin` remote points to `git@github.com:CodeDailyHenry/transwarp-service-insight-rebuild.git`, so `gh` can infer the repository when run from this checkout.

## Conventions

- **Create:** `gh issue create --title "..." --body "..."`
- **Read:** `gh issue view <number> --comments`
- **List:** `gh issue list --state open --json number,title,body,labels,comments`
- **Comment:** `gh issue comment <number> --body "..."`
- **Apply/remove labels:** `gh issue edit <number> --add-label "..."` or `--remove-label "..."`
- **Close:** `gh issue close <number> --comment "..."`

Use the filters and JSON fields appropriate to the task. For multiline content, write the body safely without losing formatting.

## Pull requests as a triage surface

**PRs as a request surface: no.**

If this is changed to `yes`, external pull requests use the same labels and states as issues. Use `gh pr view`, `gh pr diff`, `gh pr comment`, `gh pr edit`, and `gh pr close` as appropriate.

GitHub shares one number space across issues and pull requests. If `#42` is ambiguous, try `gh pr view 42` and then `gh issue view 42`.

## Skill operations

When a skill says “publish to the issue tracker,” create a GitHub issue.

When a skill says “fetch the relevant ticket,” run:

`gh issue view <number> --comments`

## Wayfinding operations

The wayfinding map is one issue with child issues as tickets.

- Label the map `wayfinder:map`.
- Label child tickets `wayfinder:<type>`, where type is `research`, `prototype`, `grilling`, or `task`.
- Prefer GitHub sub-issues; otherwise link children through the map task list and add `Part of #<map>` to each child.
- Prefer native GitHub issue dependencies. If unavailable, add `Blocked by: #<number>` to the child.
- Claim work with `gh issue edit <number> --add-assignee @me`.
- Resolve work by commenting with the result, closing the child, and updating the map’s decisions.
