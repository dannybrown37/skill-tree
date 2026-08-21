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

## Running it

The backfill itself is a bulk operation, and bulk operations on a live table are the part that
costs money and causes incidents. `references/bulk-operations.md` covers it in full; the two
things to know before starting:

- **Pick the tool for the size.** The `bulk` executor (Glue-backed, you supply a Python
  `generate()`) for counts, finds, backfills, diffs and mass deletes; native S3 import when a
  create-and-cut-over is on the table, since it is dramatically cheaper and loads GSIs free --
  but new tables only.
- **Always rate limit.** These commands load the whole table; a bulk delete pays RCUs to scan
  everything plus a WCU per deletion. Rate limiting avoids throttling live traffic, and in
  provisioned mode slow-and-steady is also the cheaper way to run.

## Related

- `skill-tree:dynamodb-modeling`: designing so these migrations are rare.
- `skill-tree:dynamodb-cost-audit`: deciding which of these migrations is worth running.
