# Running the migration: tooling and rate limiting

The detail behind `SKILL.md`'s "Running it" section. Read this once a migration is
decided and the question is how to execute it over a real table without throttling live
traffic or spending more than the migration is worth.

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
