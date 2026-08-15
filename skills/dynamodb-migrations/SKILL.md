---
name: dynamodb-migrations
description: "Invoke when changing a DynamoDB table that is already live: \"add a GSI\", \"backfill this attribute\", \"change the projection on an index\", \"migrate to a new key design\", \"how do I do this without downtime\", \"do we need to backfill or can we let it drift\". Ordered playbooks per evolution type, plus stream and backfill hazards."
user-invocable: true
---

# DynamoDB Migrations

Dynamo has an unfair reputation of "great, as long as your application never changes." Most
evolutions are straightforward. They just have a required order of operations, and getting
that order wrong is what turns a routine change into an outage or a double backfill.

The framing that makes every playbook below make sense: during a migration, multiple
application versions and multiple schema versions exist concurrently. Every step has to be
correct while both the old and new shape are in the table.

The general shape is always:

1. Make application code compatible with the change (read both shapes).
2. Update application code to write the new shape.
3. Optional: bulk update existing records.

## Evolution type 1: a change that doesn't affect item access

A new unindexed, un-fetched attribute, like a customer tier displayed to support agents.

The easiest case. Update the application-level schema and ship. No backfill, no index.

Watch for: schema bloat, and the long-term hygiene of downstream systems that consume these
items and now must tolerate an attribute that exists on some items and not others.

## Evolution type 2: a new index on an existing attribute

The attribute is already on every item, so there's nothing to backfill.

1. Add the index. (One index change at a time; see below.)
2. Wait for the backfill to complete.
3. Add the application access pattern.

Changing a projection is the same shape: create a new index with the projection you want,
cut reads over, drop the old index. Cheap and reversible except on very large tables, where the
backfill is the expensive part.

## Evolution type 3: a new index on a new attribute

This is the one with a mandatory order.

1. Update application code to start writing the new attribute. Do this before
   anything else, so the set of items needing migration stops growing while you migrate it.
2. Scan the table.
3. For each item that needs the new attribute, run an `UpdateItem`.
4. Once the bulk update completes, add the index and update application code to read from it.

Reversing steps 1 and 2 means finishing the backfill and immediately having a fresh population
of un-backfilled items.

## Backfill, or let it drift?

Not every migration needs a backfill. Decide on data lifetime:

- Short-lived data: if items carry a 30-day TTL, don't bother. The old shape ages out on
  its own, and you only need read-compatibility for those 30 days.
- Frequently rewritten data: if the application updates most items regularly anyway, the
  new attribute lands naturally. Confirm the tail, though. "Most items" hides the ones that
  haven't been touched in three years.
- Long-lived data: backfill. There is no drift that reaches it.

## Streams: don't feed your own migration

A backfill writes every item, and every write hits your streams. Unmanaged, this triggers the
downstream Lambdas hundreds of millions of times and can loop back into the table.

- Use stream filtering on the Lambda event source so the consumer never sees migration
  writes.
- Stamp a who-wrote-this attribute on migration writes and ignore matching records.
- Filter on the new attributes that motivated the migration, so you're not reprocessing items
  the migration didn't meaningfully change.

## The one-GSI-at-a-time constraint

Dynamo allows one index change at a time, and there is no way to queue several. In IaC this
means a multi-index change is a sequence of applies, not one. Plan it as N ordered deploys,
and expect the pipeline to fail if it tries to do two at once. There's no workaround;
patience and vigilance. (DeBrie's stated "biggest tiny ask" of the service is queued index
changes, so this may improve.)

## Migrating to multi-attribute composite keys

Synthetic `GSI1PK` / `GSI1SK` strings can rival the size of the real data: 92 bytes of key on
a 101-byte item in DeBrie's example.

- New indexes: use the multi-attribute form. Declare the real attributes as the index's
  partition/sort key components instead of concatenating them.
- Existing indexes: usually worth migrating. Create a new GSI in the new form, cut over,
  drop the old one. Run the numbers first, since the cost is WCUs to update every item, but on
  a table with heavy write volume the ongoing saving pays it back.
- Exception: overloaded indexes. A `GSI1PK` serving multiple entity patterns can't be
  expressed as multi-attribute composite keys. Leave those alone.

## Hard migrations

These are hard no matter when you do them:

- Changing a primary key. Key values are immutable; a change means delete and re-insert
  every affected item.
- Combining or splitting items.
- Consolidating tables, e.g. unwinding a one-entity-per-table design into shared item
  collections. The speedups and RCU savings are real, but the path is a dual-write window:
  write both shapes for a period, migrate reads, then retire the old. DeBrie considered this
  the topic for a full talk and judged it too big for one session. Treat it as a project, not
  a ticket.

The more normalized the model, the easier every one of these gets.

## Uniqueness on a non-key attribute

The recurring hard requirement: a username is the key, but email must also be unique.

- Write two items in one transaction: the record, plus a sentinel item keyed on the email,
  with a condition that the sentinel doesn't already exist.
- If the unique attribute is optional, write the second item only when the value exists.
  This is why it can't be modeled as a key: a key can't be absent.
- Migrating an existing table into this scheme is a dual-write window like any other.

## Tooling

- Bulk executor (open-sourced by Jason Hunter's team). Feels like a local CLI, runs an AWS
  Glue Spark job for massive parallelism:

  ```bash
  bulk count  --table t --where "a > b and ts < '2024' and val = ('x' or 'y')"   # Spark SQL syntax
  bulk find   --table t --orderby timestamp --limit 100                          # no GSI required
  bulk update --table t --generator gsi-backfill                                 # your Python generate()
  bulk fill   --table t --generator fakeusers --numitems 100000000               # load test data
  bulk diff   --table t --table2 t2 --sample-fraction 0.1                        # 10% sample diff
  ```

  It handles the parallelization; you supply a Python `generate()` function. It segments scans
  dynamically (~200 segments is the sweet spot), prints small output locally and writes large
  output to S3, and estimates cost before running.

  What it unlocks: find items matching criteria, mass-delete old items, backfill new GSI keys,
  diff two tables, play an incremental export forward or backward, and import from S3 into an
  existing table (native S3 import is new-tables-only).

- AWS Glue directly, or export to S3 + Glue, for the same work hand-rolled.

- Native S3 import: dramatically cheaper than writing items, and GSIs load free. New
  tables only, which is an argument for create-and-cut-over over in-place backfill on large
  migrations.

## Running bulk operations without setting money on fire

These commands look lightweight. They are not: they load the table to crunch it. A bulk delete
spends RCUs scanning the entire table plus a WCU per deletion.

Always rate limit. Three reasons:

1. Avoid throttling: don't starve live organic traffic. Throttles exist at both table and
   partition level.
2. Control cost: in provisioned mode, slow and steady is cheaper, and you may be filling
   otherwise-unused reserved capacity for free.
3. Test load: deliberately observe how the system behaves at a given rate.

The rate-limit recipe:

- Add `ReturnConsumedCapacity` to each request.
- Observe the `ConsumedCapacity` that comes back.
- On the next request, if running ahead of schedule, `sleep()` briefly.
- In Python, boto3 event hooks do this invisibly to the calling code.

For the Glue connector on reads, rate limiting is configuration rather than code:

```python
connection_options = {
    "dynamodb.input.tableName": table_name,
    "dynamodb.splits": "100",
    "dynamodb.consistentRead": "false",
    "dynamodb.throughput.read": "100000",
}
```

Direct access (reads or writes) depends on round-trip request rate, consumption per request,
and the number of parallel executors. We can do better than "just floor it."

Two operational notes if you write your own parallel migration script:

- Handle Ctrl-C properly. Users will hit it. Trap the interrupt and stop the remote job,
  not just the local Python process. Otherwise the expensive thing keeps running after the
  terminal looks idle.
- Accumulate errors, print the first. An error affecting every executor produces hundreds
  of identical failures. Collect them into an accumulator and surface one.

## Related

- `skill-tree:dynamodb-modeling`: designing so these migrations are rare.
- `skill-tree:dynamodb-cost-audit`: deciding which of these migrations is worth running.
