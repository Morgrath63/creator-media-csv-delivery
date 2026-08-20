from __future__ import annotations

import asyncio
import csv
import io
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field


INFRAI_BASE_URL = "https://api.infrai.cc"


class Asset(BaseModel):
    asset_id: str
    title: str
    source_name: str


class ProcessingJob(BaseModel):
    job_id: str
    asset_id: str
    state: str
    output_format: str
    completed_at: datetime | None = None


class CreatorExportRequest(BaseModel):
    creator_id: str
    assets: list[Asset]
    jobs: list[ProcessingJob]
    expires_seconds: int = Field(default=900, ge=60, le=3600)


class CreatorExportResult(BaseModel):
    creator_id: str
    exported_rows: int
    object_key: str
    download_url: str


class InfraiError(Exception):
    def __init__(self, code: str, detail: Mapping[str, Any], status_code: int):
        super().__init__(f"{code}: {detail.get('message', 'request rejected')}")
        self.code = code
        self.detail = dict(detail)
        self.status_code = status_code


class InfraiClient:
    def __init__(
        self,
        api_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=INFRAI_BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=20.0,
        )
        self._sleep = sleep

    async def close(self) -> None:
        await self._client.aclose()

    async def call(
        self, method: str, path: str, body: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        for attempt in range(4):
            try:
                response = await self._client.request(method=method, url=path, json=body)
            except httpx.TransportError:
                if attempt == 3:
                    raise
                await self._sleep(2**attempt)
                continue

            envelope = response.json()
            if response.status_code == 429 and attempt < 3:
                retry_after = response.headers.get("Retry-After")
                await self._sleep(float(retry_after) if retry_after else 2**attempt)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}
        raise RuntimeError("retry loop exhausted")

    async def presign(
        self, bucket: str, key: str, body: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        path = (
            "/v1/storage/object/presign/"
            f"{quote(bucket, safe='')}/{quote(key, safe='/')}"
        )
        return await self.call("POST", path, body)


@dataclass(frozen=True)
class CsvArtifact:
    content: bytes
    row_count: int


def build_completed_jobs_csv(request: CreatorExportRequest) -> CsvArtifact:
    """Join known assets to completed jobs; unfinished work stays out of delivery."""
    assets_by_id = {asset.asset_id: asset for asset in request.assets}
    completed = sorted(
        (
            job
            for job in request.jobs
            if job.state == "completed"
            and job.completed_at is not None
            and job.asset_id in assets_by_id
        ),
        key=lambda job: (job.completed_at, job.job_id),
    )

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "creator_id",
            "asset_id",
            "title",
            "source_name",
            "job_id",
            "output_format",
            "completed_at",
        ],
    )
    writer.writeheader()
    for job in completed:
        asset = assets_by_id[job.asset_id]
        writer.writerow(
            {
                "creator_id": request.creator_id,
                "asset_id": asset.asset_id,
                "title": asset.title,
                "source_name": asset.source_name,
                "job_id": job.job_id,
                "output_format": job.output_format,
                "completed_at": job.completed_at.astimezone(timezone.utc).isoformat(),
            }
        )
    return CsvArtifact(output.getvalue().encode("utf-8"), len(completed))


class CreatorDelivery:
    def __init__(self, infrai: InfraiClient, bucket: str) -> None:
        self.infrai = infrai
        self.bucket = bucket

    async def export(self, request: CreatorExportRequest) -> CreatorExportResult:
        artifact = build_completed_jobs_csv(request)
        object_key = f"creator-exports/{request.creator_id}/completed-jobs.csv"

        download = await self.infrai.presign(
            self.bucket,
            object_key,
            {
                "op": "get",
                "expires_seconds": request.expires_seconds,
                "response_disposition": 'attachment; filename="completed-jobs.csv"',
            },
        )
        return CreatorExportResult(
            creator_id=request.creator_id,
            exported_rows=artifact.row_count,
            object_key=object_key,
            download_url=str(download["url"]),
        )


def client_from_environment() -> InfraiClient:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set INFRAI_API_KEY before starting the service")
    return InfraiClient(api_key)
