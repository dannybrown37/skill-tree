---
name: dynamodb-modeling
description: "Invoke when designing a DynamoDB table or reviewing one before it ships: \"what should my partition key be\", \"do I need a GSI here\", \"is this single-table design right\", \"review my access patterns\", or any new table/entity in a Dynamo-backed service. Access-pattern-first modeling, key strategies, index choice, and the anti-patterns that show up in review."
user-invocable: true
---

# DynamoDB Modeling

Model before you write application code. Dynamo punishes discovering an access pattern late in
a way a relational database does not: there is no `ADD INDEX` that makes an unplanned query
cheap, and the key you chose is the one you're stuck with.

The through-line: you are designing disk operations, not tables -- every read should be one
contiguous read from one partition.

## 0. Decide Dynamo is the right call

Dynamo earns its constraints with three strengths -- operational, economic, and performance.
If the project needs none of them, the constraints are just cost, and the argument is about
the datastore rather than the schema. `references/choosing-dynamo.md` has that argument in
full, including what Dynamo is genuinely bad at.

## 1. Write the access patterns down before the schema

Modeling starts with a table of access patterns, not entities. Build this artifact first and
keep it in the repo. It is the design document, and it's what a reviewer reads:

| Pattern | Operation | Target | Filters / Projections | Notes |
| --- | --- | --- | --- | --- |
| Get user | GetItem | base table | | |
| Fetch inventory for user | Query | base table | | one item collection |
| Fetch users by guild | Query | GSI1 | project `name`, `avatar` only | |

Before filling it in, answer:

- Know your domain: what are the constraints? what's the data distribution? how big are
  the items?
- Know your access patterns: every read and every write.
- Know the API: primary key + operations + secondary indexes. That's the whole toolkit.

The `Filters / Projections` column is the one people skip. It's there to force the question
"does this index actually need every attribute?" at design time, when it's free to answer.

Check: if any row's Target is "Scan," it needs a written justification.

## 2. The API is the mental model

Primary key + operations + secondary indexes is the entire toolkit: single-item actions
(`PutItem`/`GetItem`/`UpdateItem`/`DeleteItem`, full key required, all writes), Query (many
items, one partition, 1MB per request), and Scan. Each physical partition serves 3000 RCUs /
1000 WCUs; 1 RCU per 4KB read, 1 WCU per 1KB written. `references/the-api.md` expands each.

## 3. Two meta-goals, and everything else is downstream

1. **Integrity of what you save**: a valid schema, application constraints (uniqueness,
   limits), no inconsistency when duplicating data.
2. **Reach exactly the right items**: writes need a primary key addressing exactly the
   relevant item(s); reads need primary key + indexes to filter efficiently.

## 4. Partition keys

Facts that constrain the design:

- A PK or SK may be string, number, or binary. Prefer string, it's more future-proof. Number sometimes.
- You cannot change a key value. Changing one means delete and re-insert.
- Name key attributes `PK` and `SK` -- generic, future-proof, and short, which matters because
  attribute names are stored on every item.
- Decorate the values, not the attribute names: `CUSTID#123` beats a raw `123`.
- Keys are hashed for even physical distribution. Partitions split as they grow; a single
  scorching item can be given its own partition. The search term is "split for heat."

PK strategies worth naming in review:

| Strategy | Example | Why |
| --- | --- | --- |
| Descriptive | `Zip#89109` | identify the entity type in the key |
| Multi-value | `89109#Casino` | a natural key that stores related data together |
| Sharded | `Zip#89109#0` | many items per key value, so spread the heat |

## 5. Sort keys

The sort key is what makes a Query cheap. Three strategies:

| Strategy | Example | Why |
| --- | --- | --- |
| Hierarchical | `USA#NV#LAS` | "limit to USA, or to NV, or to LAS" |
| Sorting | `1729101402` | "store data sorted by time" |
| Typed | `Name#Hunter` | "get all names, or names with a prefix" |

The base table is the white pages: trivial to find by the beginning of a value, hopeless by
the middle or end. Design keys so every query is a prefix query.

## 6. Item collections

A collection is every item sharing a partition key.

- Hard limit 10GB per collection (LSIs count toward it).
- Only co-locate items retrieved together; sharing a partition key with an item you never
  fetch in the same request buys nothing.
- Single-table design is a good default, not a mandate. Don't push unrelated entities into one
  table for the aesthetics of it. The "kitchen-sink item collection" is a named anti-pattern,
  and so is the over-normalized model at the other extreme.

## 7. Secondary indexes

GSIs are the yellow pages: find things by category, as long as you categorized them.

- Prefer GSIs. An LSI is a one-way door -- creatable only with the table, and it binds the
  collection's 10GB limit -- whose one real advantage is strong consistency.
- GSIs are eventually consistent only. That's half the read price, and fine for
  user-driven flows, since nobody clicks fast enough to observe the lag. Machine-driven flows
  are a different question; check whether a stale read breaks the caller. If it does, either
  use a second base-table item or accept an LSI's downsides deliberately.
- Indexes enable additional read-based patterns only.
- Add indexes one at a time; they can be added to a live table whenever.

Check, per index: do I need the index? do I need all items in it? do I need the full item in
it? `references/index-design.md` answers each at length -- multi-attribute composite keys over
synthetic `GSI1PK` strings, selective projection, and when to reuse an index instead.

## 8-10. What the application still has to do

The table design doesn't cover any of this, and `references/application-rules.md` has it in
full:

- **Schema-less is not schema-free.** Validate on the way in *and* out, and hard-error on a
  failed parse rather than continuing.
- **Duplicating data** is legitimate; copying a mutable attribute without an answer to "how
  do I find every copy when it changes" is a future inconsistency.
- **Use the basics.** Single-item actions, Query, secondary indexes -- then transactions,
  sparingly, for low-volume high-value operations.

## 11. Anti-patterns

1. Kitchen-sink item collection, and its opposite, the over-normalized model.
2. Hiding the API behind a SQL-flavored abstraction or an ORM. It makes the mental model
   opaque and produces bad designs; the related failure is never using the full API.
3. Strongly consistent reads as a default: double the price, rarely the requirement.
4. Large items: every update pays the full item size.
5. Overuse of `TransactWriteItems`.

## 12. What Dynamo is genuinely bad at

Aggregations, and complex filtering on several optional properties. If a core requirement is
one of those, that's a datastore argument -- see `references/choosing-dynamo.md`.

## Related

- `skill-tree:dynamodb-cost-audit`: for an existing table or a bill that hurts.
- `skill-tree:dynamodb-migrations`: for changing a table that's already live.
