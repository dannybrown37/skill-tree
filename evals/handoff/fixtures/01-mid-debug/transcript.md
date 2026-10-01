**User:** `test_due_date_rollover` fails in CI maybe 1 in 5 runs. Never locally. Can you figure out what's going on? Branch is already `fix/due-date-flake`.

**Assistant:** I'll start by trying to reproduce it locally.

> `$ for i in $(seq 20); do uv run pytest tests/test_due.py -q 2>&1 | tail -1; done`
> ```
> 2 passed in 0.02s
> (x20)
> ```

0/20 locally. Let me look at the failing CI runs.

> `$ gh run list --workflow ci.yml --status failure -L 5`
> ```
> X  fix: tidy schedule  ci  main  8812345  1m2s  2026-09-19T23:47:12Z
> X  chore: bump pytest   ci  main  8809911  58s   2026-09-18T23:52:40Z
> X  feat: net60 terms    ci  main  8801002  1m5s  2026-09-15T23:41:03Z
> ```

All three failures started between 23:40 and 23:55 UTC. That's a strong hint: time-of-day, not randomness.

> `$ gh run view 8812345 --log-failed | grep -A6 'def test_due_date_rollover'`
> ```
> >       assert days_until_due(issued, "net15") == 15
> E       assert 16 == 15
> ```

Off by one day, the long way. My first guess is DST, since mid-September is close to some DST transitions. Checking the runner's timezone:

> `$ gh run view 8812345 --log | grep -i 'timezone\|TZ='`
> ```
> Runner timezone: America/Los_Angeles
> ```

The runner is on Pacific time, so DST isn't it: there's no transition on those dates, and all three failing dates are ordinary days. **Ruling out DST.** The real issue: `compute_due_date` compares `issued_at.date()` (a UTC-aware datetime in the test) against `date.today()`, which is *local* time. From 23:40 UTC onward, Pacific time is still the previous calendar day, so the two sides disagree by a day.

Let me confirm by faking the clock locally:

> `$ TZ=America/Los_Angeles faketime '2026-09-27 16:50:00' uv run pytest tests/test_due.py -q`
> ```
> F.
> E       assert 16 == 15
> ```

Reproduced. (`faketime` here takes local time: 16:50 PDT = 23:50 UTC.)

**User:** Nice. How do we fix it?

**Assistant:** Two parts: the test is fragile, and the code mixes naive-local and aware-UTC dates. Quickest test-side fix first: monkeypatch `time.time` so `date.today()` sees a fixed instant.

> Edited `tests/test_due.py`, adding `monkeypatch.setattr(time, "time", lambda: 1790000000.0)`
>
> `$ TZ=America/Los_Angeles faketime '2026-09-27 16:50:00' uv run pytest tests/test_due.py -q`
> ```
> F.
> E       assert 16 == 15
> ```

Still fails. CPython's `date.today()` is implemented in C and reads the clock directly; it doesn't go through the Python-level `time.time`, so the monkeypatch never reaches it. **Monkeypatching `time.time` doesn't work here.** Reverting that edit.

> `$ git checkout tests/test_due.py`

The usual answer is `freezegun`, which patches the `datetime` classes themselves. Shall I add it as a dev dependency?

**User:** No. We're keeping dev deps to pytest only, that's a hard rule on this repo. Inject a clock instead, the code shouldn't be calling today() directly anyway.

**Assistant:** Agreed, that's the better design. Plan:

1. `compute_due_date` and `days_until_due` take `clock: Callable[[], datetime]`, defaulting to `datetime.now(UTC)`.
2. Normalize `issued_at` to UTC before taking `.date()`, so both sides of the comparison are UTC calendar days.
3. Update callers in `schedule.py`.
4. Rewrite `test_due_date_rollover` to pass a fixed clock at 23:50 UTC. That makes the test deterministic, so no faketime is needed in CI.

Doing 1 and 2 now.

> Edited `src/invoicer/due.py`: added `Clock` alias, `_utc_now`, and a `clock` param on both functions; `issued_at.astimezone(UTC).date()`.
>
> `$ uv run python -c "from invoicer.due import compute_due_date; import inspect; print(inspect.signature(compute_due_date))"`
> ```
> (issued_at: datetime.datetime, terms: str, clock: Callable[[], datetime.datetime] = <function _utc_now at 0x7f...>)
> ```

While reading `schedule.py` for the callers, I noticed something unrelated: `money.format_currency` uses `ROUND_HALF_EVEN`, so `$2.675` renders as `$2.68` but `$2.665` renders as `$2.66`. The invoice PDF totals use half-up elsewhere, which could explain the one-cent mismatches people have reported.

**User:** Huh, yeah that's probably the penny bug. Not now though, write it down for later. Stay on the flake.

**Assistant:** Noted for later. Back to callers. `schedule.py` has two:

> `$ grep -n "compute_due_date\|days_until_due\|now()" src/invoicer/schedule.py`
> ```
> 3:from invoicer.due import compute_due_date, days_until_due
> 10:        remaining = days_until_due(issued_at, inv["terms"])
> 19:        due = compute_due_date(inv["issued_at"], inv["terms"])
> 20:        if due < datetime.now().date():
> ```

Line 10 works unchanged with the default clock. Line 20 has the same bug in a second place: a naive local `datetime.now().date()` compared against a UTC due date. `overdue()` needs to accept a `clock` and use `clock().date()` there. I haven't changed `schedule.py` yet.

One question before I touch storage: are `issued_at` values in the database stored naive or aware? If they're naive-but-UTC, `astimezone(UTC)` will treat them as *local* and shift them, which would be a new bug.

**User:** Good question, I honestly don't know. Let me ask the billing team, I'll get back to you. Don't guess on that one.

**Assistant:** Understood. That stays open, and I won't make any assumption about stored `issued_at` in the meantime.

**User:** I'm about out of time and you're getting low on context too. Let's wrap up here, write a handoff so the next session can pick this up.
