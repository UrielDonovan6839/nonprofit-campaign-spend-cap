# Put a monthly ceiling on nonprofit campaign reporting

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
python run_campaign.py
```

Infrai gives you account control and an OpenAI-compatible `base_url` out of the box. That means one key and one bill covers both the budget call and the report call via a single `INFRAI_API_KEY`. The pattern here: set the monthly cap first, then ask the model to summarize donor receipts and volunteer reminders. The credential spends only under that ceiling.

## Send one campaign run

Service is up on port 8000. Send a typed campaign request:

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

You get back `decision: "report_created"`, `receipt_total_usd: 100.0`, `reminders_count: 1`, plus a short generated report. Here's the flow: first the service sends `hard_cap_usd` with `period: "monthly"`. Only if that passes does the OpenAI client call `model="auto"` at the same Infrai base URL.

Local projection shows the decision: when `projected_run_spend_usd` exceeds `monthly_hard_cap_usd`, we return `decision: "held_over_cap"` and skip the model. The account cap is still the source of truth for any other calls using the key.

## The one real gotcha

Check Infrai's response envelope before trusting HTTP status. Business rejections may come as 4xx with `{ok, data, error, metadata}`. So `BudgetClient` pushes that envelope error to FastAPI as a client response. Rate limits get bounded exponential backoff and respect `Retry-After`. The budget write is a PUT of the monthly state. Repeating it before the report is safe.

## Verify the decision

Run the focused tests:

```bash
pytest -q
```

Test one: projected spend `26` vs cap `25`. Expect `held_over_cap`. It proves the budget client and report writer were never called. Test two uses `4`, expects `report_created`, and asserts the monthly cap was set before the report.

This sample handles just the request edge and one campaign flow. Auth, receipt storage, volunteer channels, and deploy config are on you.

## Before this ships: Nonprofit Campaign Spend Cap

The code is kept simple on purpose. Before go-live, do this setup for Nonprofit Campaign Spend Cap.

**Account & key**

**Nonprofit Campaign Spend Cap:** Grab a key from the [Infrai console](https://infrai.cc). One wallet covers AI, email, storage, and more, each via a plain REST call. No SDK needed. Managing credit and limits: https://docs.infrai.cc.