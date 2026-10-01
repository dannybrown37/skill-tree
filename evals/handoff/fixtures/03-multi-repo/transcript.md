*(Session started in `~/work/ledger-api`. `ledger-web` is a sibling checkout at `../ledger-web`.)*

**User:** We're renaming `amount_cents` to `amount_minor` in the invoice API. The name is wrong for JPY and for currencies with three minor digits. Needs to go through the API and the web client. API first.

**Assistant:** On `feat/amount-minor` in ledger-api.

> Edited `app/serializers.py`: emit `amount_minor`

**User:** Careful. If the API stops sending `amount_cents` before the web client is deployed, prod breaks. Both fields must be served until ledger-web ships, and we only drop `amount_cents` in the release after 2026-10-15.

**Assistant:** Right. I'm keeping `amount_cents` as a deprecated alias with the same value, plus a comment saying when it can go.

> `$ git commit -am "feat: add amount_minor, keep amount_cents alias"`
>
> `$ gh pr create --fill --base main`
> ```
> https://github.com/acme/ledger-api/pull/214
> ```
>
> `$ gh pr checks 214 --watch`
> ```
> ✓ test  ✓ lint  ✓ typecheck
> ```

API PR #214 is open and green. Moving to the web client.

> `$ cd ../ledger-web && git checkout -b chore/amount-minor`

Rather than hand-editing types, I'll try generating them from the API's OpenAPI spec with `openapi-typescript`, which should prevent drift like this in future.

> `$ npx openapi-typescript http://localhost:8081/openapi.json -o src/api/generated.ts`
>
> `$ npx tsc --noEmit`
> ```
> src/api/types.ts:1:18 - error TS2300: Duplicate identifier 'Invoice'.
> ... 41 more errors
> ```

The generated types collide with the hand-written `src/api/types.ts` all over the codebase, and untangling that is a project in itself. **Abandoning openapi-typescript for this change.** Deleted `generated.ts`; hand-editing instead.

Side note: the API dev server is on **port 8081**, not the 8080 in the README, because 8080 is taken by the local Keycloak container. The web dev server needs `VITE_API_URL=http://localhost:8081`.

> Edited `src/api/types.ts`: `amount_cents` → `amount_minor`
>
> Edited `src/components/InvoiceRow.tsx`: uses `inv.amount_minor`
>
> `$ npx tsc --noEmit`
> ```
> src/pages/Summary.tsx:4:48 - error TS2339: Property 'amount_cents' does not exist on type 'Invoice'.
> ```

One usage left, in `src/pages/Summary.tsx`. Let me also make sure `formatMoney` is right for JPY, since it divides by 100...

**User:** Don't go down the formatMoney road now, the JPY display fix is a separate ticket. Just note it. And I need to stop here, context is getting long. Handoff please. The next session will start in ledger-api again.
