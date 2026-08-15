---
name: dynamodb-modeling
description: "Invoke when designing a DynamoDB table or reviewing one before it ships: \"what should my partition key be\", \"do I need a GSI here\", \"is this single-table design right\", \"review my access patterns\", or any new table/entity in a Dynamo-backed service. Access-pattern-first modeling, key strategies, index choice, and the anti-patterns that show up in review."
user-invocable: true
---

# DynamoDB Modeling

Model before you write application code. Dynamo punishes discovering an access pattern late in
a way that a relational database does not. There is no `ADD INDEX` that makes an unplanned
query cheap, and the key you chose is the one you're stuck with.

The through-line: you are designing disk operations, not tables. Every read should be one
contiguous read from one partition.

## 0. Decide Dynamo is the right call

Dynamo earns its constraints through three strengths. If the project needs none of them, the
constraints are just cost:

- Operational: fully managed, effectively cannot be taken down, hands-off.
- Economic: consumption-based pricing, so the bill scales with actual use and is
  predictable. Efficiency and cost are tightly coupled.
- Performance: consistent latency at any scale. "Solve it right for one user and it works
  for a trillion."

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

One contiguous disk operation from an unbounded amount of storage:

- Single-item actions: `PutItem` / `GetItem` / `UpdateItem` / `DeleteItem`. Require the
  full primary key. All writes are single-item actions.
- Query: fetch many, composite primary key only. Requires the partition key; sort key
  optional. 1MB limit per request.
- Scan: fetch all. Use sparingly, but see the cost skill: for legitimately rare access, a
  scan can beat maintaining an index.

Each physical partition serves 3000 RCUs / 1000 WCUs. 1 RCU per 4KB read, 1 WCU per 1KB
written.

## 3. Two meta-goals, and everything else is downstream

1. Maintain the integrity of the data you're saving: have a valid schema, maintain
   application constraints (uniqueness, limits), and avoid inconsistency when duplicating data.
2. Make it easy to operate on the proper data when you need it: writes need a primary key
   that addresses exactly the relevant item(s); reads need primary key + indexes to filter
   efficiently.

## 4. Partition keys

Facts that constrain the design:

- A PK or SK may be string, number, or binary. Prefer string, it's more future-proof. Number sometimes.
- You cannot change a key value. Changing one means delete and re-insert.
- Give the key attributes short, generic, descriptive names: `PK` and `SK`. Future-proof, and
  short names matter because attribute names are stored on every item.
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
- Only co-locate items that are retrieved together. There is no benefit to sharing a
  partition key with an item you never fetch in the same request.
- Single-table design is a good default, not a mandate. Don't push unrelated entities into one
  table for the aesthetics of it. The "kitchen-sink item collection" is a named anti-pattern,
  and so is the over-normalized model at the other extreme.

## 7. Secondary indexes

GSIs are the yellow pages: find things by category, as long as you categorized them.

- Prefer GSIs. Understand LSIs fully before using one. An LSI is a one-way door (it can
  only be created with the table, and it binds the collection's 10GB limit) with serious
  downsides. Its one real advantage is strong consistency.
- GSIs are eventually consistent only. That's half the read price, and fine for
  user-driven flows, since nobody clicks fast enough to observe the lag. Machine-driven flows
  are a different question; check whether a stale read breaks the caller. If it does, either
  use a second base-table item or accept an LSI's downsides deliberately.
- Indexes enable additional read-based patterns only.
- Add indexes one at a time; they can be added to a live table whenever.

### Use multi-attribute composite keys

Declare up to 4 real attributes each as the index's partition key and sort key, instead of
hand-concatenating them into a synthetic `GSI1PK` / `GSI1SK` string.

```
Old:  GSI1PK = "WH#W2#ASSIGNEE#A17#STATUS#PICKING"
      GSI1SK = "PRI#4#CREATED#2025-11-24T13:10:32Z#ORDER#10005"

New:  PK attributes = WarehouseId, AssigneeId, Status
      SK attributes = Priority, CreatedAt
```

In DeBrie's example item, the real data was 101 bytes and the two synthetic key attributes were
92 bytes, so the index keys nearly doubled the item. Synthetic keys also bloat items, add
modeling and update complexity, and force zero-padding hacks to make numbers sort.

Rules for the multi-attribute form:

- Up to 4 attributes each for the partition key and the sort key.
- A Query must supply all partition key attributes; sort key conditions are optional.
- Sort key attributes follow SQL composite-index rules: left-to-right, no skipping.
- Scalars only (string, number). No zero-padding needed, numbers sort as numbers.
- It won't fix an overloaded index. If `GSI1PK` carries multiple entity patterns, that
  index stays synthetic. Default to multi-attribute for everything else, including new indexes
  on existing tables.

### Projections

Projecting the whole item is the easy default and fine for maybe 90% of tables. Selective
projection wins when items are large or the table is huge:

- Every write to a secondary index consumes WCUs, and writes cost 5–20x what reads do.
- Fewer projected attributes means fewer base-table updates propagate at all. If `bio` isn't in
  the index, changing `bio` triggers no index write.
- Fewer attributes means smaller pages, so fewer RCUs per query.
- The cost of getting it wrong is low: create a new GSI with the projection you want, cut over,
  drop the old one. The exception is a massive table, where the backfill is the expensive part.
  Think harder up front there.

### Don't add an index you don't need

Reuse an existing index when:

1. Read patterns overlap heavily. "Active Orders for Restaurant" is "Orders for
   Restaurant" plus a time range and a filter. Don't index it separately.
2. The search space is small. "Admin users within all users." Rule of thumb: if the whole
   candidate set is under 1MB (one Dynamo page), query and filter.

Sparse indexes are the sharp tool here: index only the items carrying some attribute, and the
bigger the table, the more the sparse index earns.

Check: for each index, answer all three. Do I need the index? Do I need all items in it?
Do I need the full item in it?

## 8. Schema-less is not schema-free

Dynamo doesn't enforce a schema, which means your application must:

- Validate data going into the database and coming out of it. (Zod, or the equivalent
  in your language.)
- Throw a hard error when parse fails on retrieval. Continuing past a failed parse is how
  a corrupt row becomes a corrupt table.

## 9. Duplicating data

Denormalization is legitimate, but answer these before you copy an attribute:

- Is this data immutable? (If yes, copy freely.)
- If not: how many times will it be copied? How do I find every copy when it changes? How fast
  must the copies converge, same request or async?

If you can't answer the second one, you don't have a denormalization, you have a future
inconsistency.

## 10. Use the basics

A novice does too much; a master uses the fewest motions possible.

- Single-item actions for single items.
- Query for list operations.
- Secondary indexes for additional read patterns.
- Transactions for the rest, sparingly, and specifically for low-volume, high-value
  operations. They cost 2x a normal write. Most teams over-correct in one direction or the
  other; the classic good use is a uniqueness constraint on a non-key attribute (write the item
  and a sentinel item in one transaction).

## 11. Anti-patterns

1. Kitchen-sink item collection, and its opposite, the over-normalized model.
2. Hiding the DynamoDB API behind a SQL-flavored abstraction or an ORM-shaped wrapper. It
   makes the mental model opaque and produces bad designs. Use Dynamo like Dynamo. The related
   failure is never using the full API.
3. Strongly consistent reads as a default: double the price, rarely the requirement.
4. Large items: every update pays the full item size.
5. Overuse of `TransactWriteItems`.

## 12. What Dynamo is genuinely bad at

These are hard whether you plan for them up front or discover them later. If a core requirement
is on this list, that's an argument about the datastore, not the schema:

- Aggregations: "how many transactions per month," "largest purchase by customer."
  (Pre-aggregate on write, or stream to something else.)
- Complex filtering: filtering or sorting by 2+ properties that are all optional.
  "All trips by company X where departure = OMA and miles > 500 and date between A and B."

Otherwise, Dynamo handles change better than its reputation suggests. See
`skill-tree:dynamodb-migrations`. The changes that stay hard are changing a primary key and
combining/splitting items; the more normalized the model, the easier evolution gets.

## Related

- `skill-tree:dynamodb-cost-audit`: for an existing table or a bill that hurts.
- `skill-tree:dynamodb-migrations`: for changing a table that's already live.
