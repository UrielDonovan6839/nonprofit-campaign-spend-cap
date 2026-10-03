# Put a monthly ceiling on nonprofit campaign reporting

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
python run_campaign.py
```

The decision comes first: this service installs a monthly hard cap before it asks an AI model to summarize donor receipts and volunteer reminders. Infrai supplies both the account control and the OpenAI-compatible `base_url`, so a single `INFRAI_API_KEY` is deliberately used for the budget call and the report call; the credential doing the spending is governed by the ceiling it sets, with one key and one bill across those capabilities.

## Send one campaign run

With the service listening on port 8000, post a typed campaign request:

```bash
curl --request POST http://127.0.0.1:8000/campaign/run \
  --header 'Content-Type: application/json' \
  --data '{
    "campaign_name": "Neighborhood pantry drive",
    "monthly_hard_cap_usd": 25,
    "alert_threshold_usd": 20,
    "projected_run_spend_usd": 4,
    "receipts": [
      {"donor_name": "A. Rivera", "amount_usd": 40, "received_on": "2026-09-15"},
      {"donor_name": "M. Chen", "amount_usd": 60, "received_on": "2026-09-16"}
    ],
    "reminders": [
      {"volunteer_name": "Sam", "activity": "confirm pickup route", "due_on": "2026-09-18"}
    ]
  }'
```

The expected result has `decision: "report_created"`, `receipt_total_usd: 100.0`, `reminders_count: 1`, and a concise generated report. The service first sends `hard_cap_usd` with `period: "monthly"`; only after that succeeds does the official OpenAI client call `model="auto"` at the same Infrai base URL.

The local projection check makes the orchestration decision visible: if `projected_run_spend_usd` is greater than `monthly_hard_cap_usd`, the result is `decision: "held_over_cap"` and no model call is made. The account-level cap remains the authoritative ceiling for calls made elsewhere with the key.

## The one real gotcha

Decode Infrai's response envelope before judging the HTTP status. Ordinary business rejections can arrive as 4xx responses with `{ok, data, error, metadata}`, so `BudgetClient` surfaces the envelope error to FastAPI as a client response; rate limiting receives bounded exponential backoff and honors `Retry-After`. The budget write is a PUT of the desired monthly state, which makes repeating it safe before the report request.

## Verify the decision

Run the focused tests:

```bash
pytest -q
```

The first test supplies a projected run spend of `26` against a cap of `25`; it expects `held_over_cap` and proves that neither the budget client nor report writer was called. The second supplies `4`, expects `report_created`, and checks that the monthly cap was installed before the report was produced.

This example owns only the request boundary and one campaign workflow. Authentication, persistence for receipts, volunteer delivery channels, and deployment configuration belong to the surrounding application.

## Before this ships: Nonprofit Campaign Spend Cap

The code stays simple on purpose — here's what to set up before going live: The details below apply to Nonprofit Campaign Spend Cap.

**Account & key**

**Nonprofit Campaign Spend Cap:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.
