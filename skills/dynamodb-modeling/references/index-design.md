# Secondary index design

The detail behind `SKILL.md` §7. Read it when you're actually specifying an index -- picking
its keys, deciding what it projects, or arguing that it shouldn't exist.

## Multi-attribute composite keys

Declare up to 4 real attributes each as the index's partition key and sort key, instead of
hand-concatenating them into a synthetic `GSI1PK` / `GSI1SK` string.

```
Old:  GSI1PK = "WH#W2#ASSIGNEE#A17#STATUS#PICKING"
      GSI1SK = "PRI#4#CREATED#2025-11-24T13:10:32Z#ORDER#10005"

New:  PK attributes = WarehouseId, AssigneeId, Status
      SK attributes = Priority, CreatedAt
```

In DeBrie's example item, the real data was 101 bytes and the two synthetic key attributes
were 92 bytes, so the index keys nearly doubled the item. Synthetic keys also bloat items, add
modeling and update complexity, and force zero-padding hacks to make numbers sort.

Rules for the multi-attribute form:

- Up to 4 attributes each for the partition key and the sort key.
- A Query must supply all partition key attributes; sort key conditions are optional.
- Sort key attributes follow SQL composite-index rules: left-to-right, no skipping.
- Scalars only (string, number). No zero-padding needed, numbers sort as numbers.
- It won't fix an overloaded index. If `GSI1PK` carries multiple entity patterns, that index
  stays synthetic. Default to multi-attribute for everything else, including new indexes on
  existing tables.

## Projections

Projecting the whole item is the easy default and fine for maybe 90% of tables. Selective
projection wins when items are large or the table is huge:

- Every write to a secondary index consumes WCUs, and writes cost 5-20x what reads do.
- Fewer projected attributes means fewer base-table updates propagate at all. If `bio` isn't
  in the index, changing `bio` triggers no index write.
- Fewer attributes means smaller pages, so fewer RCUs per query.
- The cost of getting it wrong is low: create a new GSI with the projection you want, cut
  over, drop the old one. The exception is a massive table, where the backfill is the
  expensive part. Think harder up front there.

## Don't add an index you don't need

Reuse an existing index when:

1. **Read patterns overlap heavily.** "Active Orders for Restaurant" is "Orders for
   Restaurant" plus a time range and a filter. Don't index it separately.
2. **The search space is small.** "Admin users within all users." Rule of thumb: if the whole
   candidate set is under 1MB (one Dynamo page), query and filter.

Sparse indexes are the sharp tool here: index only the items carrying some attribute, and the
bigger the table, the more the sparse index earns.
