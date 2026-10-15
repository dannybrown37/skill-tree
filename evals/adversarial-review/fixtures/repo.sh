#!/usr/bin/env bash
# Builds a repo whose feature branch tracks origin/main, so the skill's
# "diff against the upstream" step has a real base. Takes the variant of
# batching.py the branch adds: "buggy" drops a trailing partial batch,
# "sound" does not.
set -euo pipefail

variant="$1"

commit() {
	git -c user.name=eval -c user.email=eval@example.invalid add -A
	git -c user.name=eval -c user.email=eval@example.invalid commit -qm "$1"
}

cat >README.md <<'EOF2'
# batcher
Send records to the ingest API in batches.
EOF2

cat >send.py <<'EOF2'
def send(records: list[dict]) -> int:
    return len(records)
EOF2

git init -q -b main
commit 'chore: init'
git init -q --bare .git/eval-origin
git remote add origin .git/eval-origin
git push -q origin main
git switch -q -c feat/batching
git branch -q --set-upstream-to=origin/main

if [[ "${variant}" == buggy ]]; then
	body='    return [items[i : i + size] for i in range(0, len(items) - size + 1, size)]'
else
	body='    return [items[i : i + size] for i in range(0, len(items), size)]'
fi

cat >batching.py <<EOF2
def batched(items: list, size: int) -> list[list]:
    """Split items into consecutive batches of at most size items."""
    if size < 1:
        raise ValueError(f"size must be at least 1, got {size}")
${body}
EOF2

cat >send.py <<'EOF2'
from batching import batched


def send(records: list[dict], batch_size: int = 100) -> int:
    sent = 0
    for batch in batched(records, batch_size):
        sent += len(batch)
    return sent
EOF2

cat >test_batching.py <<'EOF2'
import unittest

from batching import batched


class BatchedTest(unittest.TestCase):
    def test_even_split(self) -> None:
        self.assertEqual(batched([1, 2, 3, 4], 2), [[1, 2], [3, 4]])

    def test_rejects_zero(self) -> None:
        with self.assertRaises(ValueError):
            batched([1], 0)


if __name__ == "__main__":
    unittest.main()
EOF2

cat >>README.md <<'EOF2'

`send()` batches 100 records per request.
EOF2

commit 'feat: send records in batches'
