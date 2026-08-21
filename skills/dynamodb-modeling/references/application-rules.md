# Rules for the application on top of the table

The detail behind `SKILL.md` §8-10. These are about what the code around Dynamo has to
do, rather than how the keys are shaped -- read them when reviewing the data access
layer, not when picking a partition key.

## Schema-less is not schema-free

Dynamo doesn't enforce a schema, which means your application must:

- Validate data going into the database and coming out of it. (Zod, or the equivalent
  in your language.)
- Throw a hard error when parse fails on retrieval. Continuing past a failed parse is how
  a corrupt row becomes a corrupt table.

## Duplicating data

Denormalization is legitimate, but answer these before you copy an attribute:

- Is this data immutable? (If yes, copy freely.)
- If not: how many times will it be copied? How do I find every copy when it changes? How fast
  must the copies converge, same request or async?

If you can't answer the second one, you don't have a denormalization, you have a future
inconsistency.

## Use the basics

A novice does too much; a master uses the fewest motions possible.

- Single-item actions for single items.
- Query for list operations.
- Secondary indexes for additional read patterns.
- Transactions for the rest, sparingly, and specifically for low-volume, high-value
  operations. They cost 2x a normal write. Most teams over-correct in one direction or the
  other; the classic good use is a uniqueness constraint on a non-key attribute (write the item
  and a sentinel item in one transaction).
