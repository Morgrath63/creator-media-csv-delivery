from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from media_export import (
    CreatorDelivery,
    CreatorExportRequest,
    CreatorExportResult,
    InfraiError,
    client_from_environment,
)


app = FastAPI(title="Creator media CSV delivery")


@app.post("/exports", response_model=CreatorExportResult)
async def create_export(request: CreatorExportRequest) -> CreatorExportResult:
    infrai = client_from_environment()
    delivery = CreatorDelivery(
        infrai=infrai,
        bucket=os.environ.get("INFRAI_EXPORT_BUCKET", "creator-media-exports"),
    )
    try:
        return await delivery.export(request)
    except InfraiError as exc:
        client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=client_status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    finally:
        await infrai.close()

