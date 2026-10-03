import asyncio
from typing import Any

from nonprofit_service import CampaignRunRequest, CampaignWorkflow


class RecordingBudgetClient:
    def __init__(self) -> None:
        self.calls: list[tuple[float, float | None]] = []

    async def set_monthly_cap(
        self, hard_cap_usd: float, alert_threshold_usd: float | None
    ) -> dict[str, Any]:
        self.calls.append((hard_cap_usd, alert_threshold_usd))
        return {"hard_cap_usd": hard_cap_usd, "period": "monthly"}


def campaign(projected_run_spend_usd: float) -> CampaignRunRequest:
    return CampaignRunRequest(
        campaign_name="Neighborhood pantry drive",
        monthly_hard_cap_usd=25.0,
        alert_threshold_usd=20.0,
        projected_run_spend_usd=projected_run_spend_usd,
        receipts=[
            {"donor_name": "A. Rivera", "amount_usd": 40.0, "received_on": "2026-09-15"},
            {"donor_name": "M. Chen", "amount_usd": 60.0, "received_on": "2026-09-16"},
        ],
        reminders=[
            {
                "volunteer_name": "Sam",
                "activity": "confirm pickup route",
                "due_on": "2026-09-18",
            }
        ],
    )


def test_holds_report_before_any_spending_when_projection_exceeds_cap() -> None:
    budget = RecordingBudgetClient()
    reports: list[str] = []
    workflow = CampaignWorkflow(budget, lambda _: reports.append("called") or "report")

    result = asyncio.run(workflow.run(campaign(projected_run_spend_usd=26.0)))

    assert result.decision == "held_over_cap"
    assert result.receipt_total_usd == 100.0
    assert budget.calls == []
    assert reports == []


def test_sets_cap_then_builds_campaign_report() -> None:
    budget = RecordingBudgetClient()
    workflow = CampaignWorkflow(budget, lambda _: "Receipts logged; one reminder due.")

    result = asyncio.run(workflow.run(campaign(projected_run_spend_usd=4.0)))

    assert result.decision == "report_created"
    assert result.report == "Receipts logged; one reminder due."
    assert budget.calls == [(25.0, 20.0)]
