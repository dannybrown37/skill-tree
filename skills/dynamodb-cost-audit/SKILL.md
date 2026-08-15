---
name: dynamodb-cost-audit
description: "Invoke when a DynamoDB bill needs to come down or an existing table needs an efficiency review: \"our Dynamo costs are too high\", \"why is this table so expensive\", \"can we cut RCUs/WCUs\", \"should we be on-demand or provisioned\", \"do we still need this GSI\". Ordered audit from biggest lever to smallest, with the thresholds that decide each call."
user-invocable: true
---

# DynamoDB Cost Audit

Use less, pay less. That is the entire root of Dynamo cost work. There is no pricing tier that
saves you from a bad item shape.

Cost comes from six places. Find out which one dominates before optimizing anything: compute
capacity, storage, backups, import/export, data transfer, streams.

Work the list in order. The early items are usually worth more than everything below them
combined.

## 1. Item size, and the write amplification behind it

Every update pays the full size of the larger of the old and new item. Not the delta. This
single fact explains most surprising Dynamo bills.

The canonical failure: a streaming service kept each customer's entire watch history in one
item. Fine for most customers, ruinous for the heavy watchers, whose full item size was
rewritten on every play. $1 million a year, fixed by storing one item per watch-history
entry.

Actions, roughly in order of payoff:

- Split static data from frequently-updated data across separate items. The static half
  stops being rewritten.
- Split large collections into per-entry items. The "video game knapsack" test: if adding
  one object rewrites the whole sack, the model is wrong. Model so writes are small and the
  common read is still one Query.
- Get items under the threshold. 1 RCU per 4KB read, 1 WCU per 1KB written, and the
  rounding is brutal. 4.1KB costs 2 RCUs: 2.5% more data, 100% more cost. Auditing a table for
  items sitting just over a boundary is high-value and rarely done.
- Shorten attribute names. Dynamo is schema-less, so every attribute name is stored on
  every item. The tradeoff is real, since short names cost human mental mapping, so spend it on
  high-cardinality tables, not everywhere.
- Compress large attribute values. lz4 is the sweet spot: the compute to compress and
  decompress is more than repaid. Only for attributes that will never need to be indexed
  or filtered. Once compressed they are opaque, and that's a one-way door.
- Compress several attributes into one compressed JSON blob where the same "never
  indexed" caveat holds.
- Pre-aggregate very small items to cut write counts, but don't overshoot. Small items
  are far better than large ones; this is a narrow optimization, not a direction.

## 2. Access patterns

- Design PK/SK for direct item or collection access. A single Query returning many items
  beats N `GetItem` calls.
- Store data that is accessed together in the same item collection, and only data that is
  accessed together. Co-locating items you never fetch together buys nothing and costs
  flexibility.
- Filtering saves almost nothing. `FilterExpression` runs after the read; you already paid
  the RCUs. It saves a little transit, that's all.
- Low-cardinality partition keys (few distinct values) concentrate heat and throttle.
- Data type matters a little, since numbers store slightly smaller than strings, but it's
  noise next to item shape.
- Use transactions when you need multi-item atomicity, and only then: they cost 2x a
  normal write.

## 3. Secondary indexes

The most common quick win in the whole audit.

- GSIs that haven't been read in 30 days are surprisingly common. Audit read metrics per
  index and delete what nothing queries. Every write to a secondary index consumes WCUs, and
  writes cost 5–20x reads, so an unread index is a pure tax on every write.
- The decision rule:
  - "I want to find items using a different access pattern" → yes, index it.
  - "I need it, but extremely rarely" → no. A scan on a monthly-access pattern is cheaper
    than carrying an index through every write.
  - "I might need it" or "I needed it, but not anymore" → no. Delete it.
- Sparse GSIs index only the items carrying an attribute. The bigger the table, the bigger
  the win.
- Trim projections. Fewer projected attributes means fewer base-table writes propagate at
  all, and smaller index pages on read. Creating a replacement GSI with a tighter projection
  and dropping the old one is cheap and reversible on any table that isn't enormous.
- Replace synthetic composite keys with multi-attribute composite keys. Concatenated
  `GSI1PK`/`GSI1SK` strings can approach the size of the real data: 92 bytes of key on a
  101-byte item in a DeBrie example. Migrating an existing table means creating a new GSI in
  the new form and dropping the old; run the WCU math first, but it pays back. The exception is
  an overloaded index (one GSI serving multiple entity patterns), which can't use the new form.

## 4. Capacity mode

- On-demand maximizes elasticity and minimizes throttling. On-demand throughput pricing was
  cut 50% in November 2024, which moved the break-even a long way in its favor, so re-run any
  comparison made before that.
- Provisioned is for throughput you can actually predict. The rule of thumb: you must
  consume at least 30% of what you provision. Below that, on-demand is cheaper.
- Reserved capacity is a regional RCU/WCU commitment worth 54–77% off hourly rates. If
  the org already signs long-term AWS commitments, not having one here is usually an oversight
  rather than a decision.
- Rate-limiting bulk work into unused reserved capacity turns an expensive migration into a
  free one. See `skill-tree:dynamodb-migrations`.

## 5. Table class

Performance is identical between Standard and Standard-Infrequent Access. The choice is
purely storage-vs-throughput mix.

When storage exceeds ~42% of throughput costs, consider Standard-IA (and talk to an AWS
specialist before flipping a large table).

## 6. Storage

- TTL is free. No additional write cost, and it keeps storage flat. Use it whenever items
  have a known validity period.
- The catch: adding a TTL attribute after the fact requires backfilling every existing
  item, which is not free. So add the attribute on day one even if you're unsure. Writing an
  unused timestamp is far cheaper than a retroactive full-table update.

## 7. Backups, import, export

- Enable PITR. It technically adds cost, but it's cheaper than the backup alternatives it
  replaces and gives any point in the last 35 days.
- The 99% trick: recovering from a bad write does not require a full table restore at
  ~$150/TB. Do an incremental export across the time window of the accident instead.
  A DeBrie example came to about $1.
- Import from S3 when creating a table: a fraction of the cost of writing the items, and
  GSIs load free. New tables only, which is a reason to prefer create-and-cut-over during
  a big migration rather than in-place backfill.
- Export to S3 for anything downstream. No read costs, no ETL pipeline to maintain, since AWS
  dumps to S3 on a button press. Incremental export exists now too.

## Audit checklist

Run top to bottom; stop when the bill stops hurting.

- [ ] Which of the six cost sources dominates? (Don't skip this.)
- [ ] Any items just over a 1KB/4KB boundary?
- [ ] Any large item where a small, frequent update rewrites the whole thing?
- [ ] Any GSI with no reads in 30 days?
- [ ] Any GSI projecting attributes nobody reads from it?
- [ ] Any synthetic concatenated index keys that could be multi-attribute?
- [ ] Provisioned tables consuming under 30% of provisioned capacity?
- [ ] Reserved capacity contract in place for the steady-state floor?
- [ ] Storage over ~42% of throughput cost anywhere? (→ Standard-IA)
- [ ] Any table holding items with a known validity period and no TTL?
- [ ] PITR enabled?
- [ ] Any hand-rolled ETL that export-to-S3 would replace?

## Related

- `skill-tree:dynamodb-modeling`: the design decisions that create these bills.
- `skill-tree:dynamodb-migrations`: how to actually execute the fixes on a live table.
