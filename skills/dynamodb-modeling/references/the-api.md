# The whole DynamoDB API, as a mental model

The detail behind `SKILL.md` §2. Read it when someone is reaching for a query Dynamo
cannot do -- the toolkit really is this small, and most bad designs come from not
believing that.

## One contiguous disk operation

One contiguous disk operation from an unbounded amount of storage:

- Single-item actions: `PutItem` / `GetItem` / `UpdateItem` / `DeleteItem`. Require the
  full primary key. All writes are single-item actions.
- Query: fetch many, composite primary key only. Requires the partition key; sort key
  optional. 1MB limit per request.
- Scan: fetch all. Use sparingly, but see the cost skill: for legitimately rare access, a
  scan can beat maintaining an index.

Each physical partition serves 3000 RCUs / 1000 WCUs. 1 RCU per 4KB read, 1 WCU per 1KB
written.
