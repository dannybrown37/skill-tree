# Is DynamoDB the right datastore?

Read this when the datastore itself is in question -- a new service, or a requirement that
keeps fighting the model. If Dynamo is already chosen and the argument is about schema, skip
it and stay in `SKILL.md`.

## What Dynamo earns its constraints with

Three strengths. If the project needs none of them, the constraints are just cost:

- **Operational**: fully managed, effectively cannot be taken down, hands-off.
- **Economic**: consumption-based pricing, so the bill scales with actual use and is
  predictable. Efficiency and cost are tightly coupled.
- **Performance**: consistent latency at any scale. "Solve it right for one user and it works
  for a trillion."

## What it is genuinely bad at

These are hard whether you plan for them up front or discover them later. If a core
requirement is on this list, that's an argument about the datastore, not the schema:

- **Aggregations**: "how many transactions per month," "largest purchase by customer."
  Pre-aggregate on write, or stream to something else.
- **Complex filtering**: filtering or sorting by 2+ properties that are all optional.
  "All trips by company X where departure = OMA and miles > 500 and date between A and B."

## What it is better at than its reputation suggests

Change. See `skill-tree:dynamodb-migrations`. The changes that stay hard are changing a
primary key and combining or splitting items; the more normalized the model, the easier
evolution gets.
