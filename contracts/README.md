# API contracts

Three clients decode the same JSON: the **backend** produces it, the **iPhone app**
decodes it with `Codable`, and the **website** decodes it with TypeScript types.
Nothing enforces that those three agree — unless something checks. This folder is
that something.

## How it works

`contracts/fixtures/*.json` holds one real example response per API shape, generated
by the backend itself:

```
make contracts          # regenerate every fixture from the live backend code
```

That runs `backend/tests/test_contracts.py` with `SPASHT_WRITE_CONTRACTS=1`, which
builds each response through the actual FastAPI app and writes it here.

Every other test run **verifies** instead of writing:

- `make test` (backend) asserts each committed fixture still has exactly the fields
  the current backend produces. Add, rename or remove a field without regenerating
  and this fails.
- `make ios-test` decodes every fixture into the app's `Codable` models. A field the
  app does not expect, or a missing one it requires, fails the build.
- the website's `vitest` run decodes the same files against `src/lib/types.ts`.

## The rule

**An API change is one commit:** change the Pydantic model, run `make contracts`,
update the iOS `Codable` models and the TypeScript types, and commit the fixtures
together with all three. A fixture diff in a pull request is the signal that client
code needs to change.

Fixtures are committed on purpose. They are the readable record of what the API
looked like, and they let the iOS tests run without a backend or a database.

## Contents

| Fixture | Shape | Added |
|---|---|---|
| `health.json` | `GET /api/health` | phase 0 |
| `error_not_found.json` | the standard error envelope (§8.1) | phase 0 |

`me.json` arrives in phase 1, and one fixture per golden-path step in phase 3.

## Conventions (build plan §8.1)

- JSON keys are **camelCase**.
- Money is **integer rupees** (`"emi": 4600`), never a float or a formatted string.
- Rates are numbers with 2 decimals (`18.67`).
- Times are ISO 8601 in UTC.
- Errors are always `{"error": {"code", "message", "requestId"}}`.

Fixtures contain synthetic data only. Values that vary per request (ids, timestamps)
are replaced with stable placeholders so a regeneration produces no diff unless the
**shape** changed.
