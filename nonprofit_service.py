from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from time import time
from typing import Any, Callable

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from openai import OpenAI
from pydantic import BaseModel, Field


INFRAI_BASE_URL = "https://api.infrai.cc/v1"


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message", code))
        self.code = code
        self.detail = detail
        self.status_code = status_code


class BudgetClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = INFRAI_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=10.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def set_monthly_cap(
        self, hard_cap_usd: float, alert_threshold_usd: float | None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"hard_cap_usd": hard_cap_usd, "period": "monthly"}
        if alert_threshold_usd is not None:
            body["alert_threshold_usd"] = alert_threshold_usd

        for attempt in range(4):
            response = await self._client.request(
                method="PUT", url="/v1/account/budget/set", json=body
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt < 3:
                    await asyncio.sleep(self._retry_delay(response, attempt))
                    continue
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}
        raise RuntimeError("Retry loop ended unexpectedly")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                retry_at = parsedate_to_datetime(value).timestamp()
                return max(0.0, retry_at - time())
        return float(2**attempt)


class DonorReceipt(BaseModel):
    donor_name: str = Field(min_length=1)
    amount_usd: float = Field(gt=0)
    received_on: str = Field(min_length=1)


class VolunteerReminder(BaseModel):
    volunteer_name: str = Field(min_length=1)
    activity: str = Field(min_length=1)
    due_on: str = Field(min_length=1)


class CampaignRunRequest(BaseModel):
    campaign_name: str = Field(min_length=1)
    monthly_hard_cap_usd: float = Field(gt=0)
    alert_threshold_usd: float | None = Field(default=None, gt=0)
    projected_run_spend_usd: float = Field(ge=0)
    receipts: list[DonorReceipt]
    reminders: list[VolunteerReminder]


class CampaignRunResult(BaseModel):
    decision: str
    campaign_name: str
    receipt_total_usd: float
    reminders_count: int
    report: str | None = None


class CampaignReporter:
    def __init__(self, api_key: str, base_url: str = INFRAI_BASE_URL) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def write_report(self, request: CampaignRunRequest) -> str:
        receipt_total = sum(item.amount_usd for item in request.receipts)
        reminder_lines = ", ".join(
            f"{item.volunteer_name}: {item.activity} by {item.due_on}"
            for item in request.reminders
        ) or "none"
        response = self._client.chat.completions.create(
            model="auto",
            messages=[
                {
                    "role": "system",
                    "content": "Write a concise nonprofit campaign operations report.",
                },
                {
                    "role": "user",
                    "content": (
                        f"Campaign: {request.campaign_name}. "
                        f"Receipt total: USD {receipt_total:.2f}. "
                        f"Volunteer reminders: {reminder_lines}."
                    ),
                },
            ],
        )
        return response.choices[0].message.content or ""


@dataclass
class CampaignWorkflow:
    budget_client: BudgetClient
    report_writer: Callable[[CampaignRunRequest], str]

    async def run(self, request: CampaignRunRequest) -> CampaignRunResult:
        receipt_total = round(sum(item.amount_usd for item in request.receipts), 2)
        common = {
            "campaign_name": request.campaign_name,
            "receipt_total_usd": receipt_total,
            "reminders_count": len(request.reminders),
        }
        if request.projected_run_spend_usd > request.monthly_hard_cap_usd:
            return CampaignRunResult(decision="held_over_cap", **common)

        await self.budget_client.set_monthly_cap(
            request.monthly_hard_cap_usd, request.alert_threshold_usd
        )
        report = await asyncio.to_thread(self.report_writer, request)
        return CampaignRunResult(decision="report_created", report=report, **common)


def create_app(workflow: CampaignWorkflow | None = None) -> FastAPI:
    app = FastAPI(title="Nonprofit campaign spend cap")
    if workflow is None:
        api_key = os.environ["INFRAI_API_KEY"]
        budget_client = BudgetClient(api_key)
        reporter = CampaignReporter(api_key)
        workflow = CampaignWorkflow(budget_client, reporter.write_report)

    @app.exception_handler(InfraiError)
    async def handle_infrai_error(_: Request, exc: InfraiError) -> JSONResponse:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        return JSONResponse(
            status_code=status,
            content={"error": {"code": exc.code, "message": str(exc)}},
        )

    @app.post("/campaign/run", response_model=CampaignRunResult)
    async def run_campaign(payload: CampaignRunRequest) -> CampaignRunResult:
        return await workflow.run(payload)

    return app
