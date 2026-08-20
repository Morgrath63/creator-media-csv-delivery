from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from media_export import (
    Asset,
    CreatorDelivery,
    CreatorExportRequest,
    ProcessingJob,
    client_from_environment,
)


async def main() -> None:
    request = CreatorExportRequest(
        creator_id="creator-42",
        assets=[
            Asset(asset_id="asset-7", title="Launch cut", source_name="launch.mov")
        ],
        jobs=[
            ProcessingJob(
                job_id="job-9",
                asset_id="asset-7",
                state="completed",
                output_format="hls",
                completed_at=datetime(2026, 8, 20, 9, 30, tzinfo=timezone.utc),
            )
        ],
    )
    infrai = client_from_environment()
    try:
        result = await CreatorDelivery(infrai, "creator-media-exports").export(request)
        print(result.model_dump_json(indent=2))
    finally:
        await infrai.close()


if __name__ == "__main__":
    asyncio.run(main())

