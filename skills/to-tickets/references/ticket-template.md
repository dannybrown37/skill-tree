# Ticket File Template

For local-file mode. One file per ticket: `docs/tickets/<feature-slug>/<NN>-<slug>.md`

```markdown
# <Title>

**Status**: ready | in-progress | done

## What to build

The end-to-end behaviour this ticket makes work, from the user's perspective.

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2

## Blocked by

- `01-<slug>` — <title>
- (or "None — can start immediately")

## Parent

<reference to the source spec or issue, if one exists>
```
