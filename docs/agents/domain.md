# Domain Docs

This repository uses a single-context domain-documentation layout.

## Before exploring

Read these resources when they exist:

- `CONTEXT.md` at the repository root
- Relevant architecture decision records under `docs/adr/`

If these resources do not exist, proceed silently. Domain-modeling workflows create them when terminology or architectural decisions are resolved.

## Layout

```text
/
├── CONTEXT.md
├── docs/
│   └── adr/
└── src/
```

## Use the glossary’s vocabulary

When naming a domain concept in issues, proposals, hypotheses, tests, or code, use the term defined in `CONTEXT.md`. Avoid synonyms that the glossary explicitly rejects.

If a necessary concept is absent, reconsider whether the project uses a different term or record the gap for domain modeling.

## Flag ADR conflicts

If proposed work contradicts an existing ADR, surface the conflict explicitly instead of silently overriding the recorded decision.
