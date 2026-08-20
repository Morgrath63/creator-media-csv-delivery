import csv
import io
import asyncio
from datetime import datetime, timezone

from media_export import (
    Asset,
    CreatorDelivery,
    CreatorExportRequest,
    ProcessingJob,
    build_completed_jobs_csv,
)


class RecordingInfrai:
    def __init__(self) -> None:
        self.calls = []

    async def presign(self, bucket, key, body):
        self.calls.append((bucket, key, body))
        return {"url": "https://download.example/report.csv"}


def test_export_includes_only_completed_jobs_with_known_assets() -> None:
    request = CreatorExportRequest(
        creator_id="creator-42",
        assets=[Asset(asset_id="asset-1", title="Episode 1", source_name="ep1.mov")],
        jobs=[
            ProcessingJob(
                job_id="job-complete",
                asset_id="asset-1",
                state="completed",
                output_format="mp4",
                completed_at=datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc),
            ),
            ProcessingJob(
                job_id="job-running",
                asset_id="asset-1",
                state="processing",
                output_format="hls",
            ),
            ProcessingJob(
                job_id="job-orphan",
                asset_id="asset-missing",
                state="completed",
                output_format="mp4",
                completed_at=datetime(2026, 8, 20, 8, 5, tzinfo=timezone.utc),
            ),
        ],
    )

    artifact = build_completed_jobs_csv(request)
    rows = list(csv.DictReader(io.StringIO(artifact.content.decode("utf-8"))))

    assert artifact.row_count == 1
    assert [row["job_id"] for row in rows] == ["job-complete"]
    assert rows[0]["title"] == "Episode 1"


def test_delivery_only_signs_an_existing_object() -> None:
    request = CreatorExportRequest(creator_id="creator-42", assets=[], jobs=[])
    infrai = RecordingInfrai()

    result = asyncio.run(CreatorDelivery(infrai, "existing-bucket").export(request))

    assert result.download_url == "https://download.example/report.csv"
    assert infrai.calls == [
        (
            "existing-bucket",
            "creator-exports/creator-42/completed-jobs.csv",
            {
                "op": "get",
                "expires_seconds": 900,
                "response_disposition": 'attachment; filename="completed-jobs.csv"',
            },
        )
    ]
