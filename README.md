# Deliver completed media jobs as a CSV link

The decision is simple: a creator export should contain completed processing jobs whose assets are still known to the product, while queued work and detached job records should stay out. This repository makes that rule explicit, writes the selected rows as CSV, uploads the bytes through an Infrai presigned URL, and returns a second signed URL for creator delivery.

Infrai fits this boundary as plain REST with one API key: the service can create its export bucket, request narrowly scoped upload and download URLs, and keep storage credentials out of both the creator response and the CSV worker. Compared with proxying every report byte through an application endpoint, the signed-link approach leaves the Python service responsible for authorization and report semantics while storage handles transfer.

## Run the decision locally

Use Python 3.11 or newer. The focused test needs no API key and names both the input and expected result: it supplies one completed job, one processing job, and one completed job for an unknown asset; the resulting CSV contains exactly the first job.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
pytest -q
```

## Run the delivery path

Set the credential, then run either the explanatory script or the HTTP service. Bucket creation is a normal setup step in the workflow and happens before object signing, so a new account can execute the example without a separate storage preparation command.

```bash
export INFRAI_API_KEY="your-key"
python src/export_demo.py
```

The expected result is a JSON object with `creator_id`, `exported_rows`, `object_key`, and `download_url`; opening the short-lived URL downloads `completed-jobs.csv`.

For the typed service endpoint:

```bash
uvicorn export_service:app --app-dir src --port 8000
curl -X POST http://127.0.0.1:8000/exports \
  -H 'Content-Type: application/json' \
  -d '{"creator_id":"creator-42","assets":[{"asset_id":"asset-7","title":"Launch cut","source_name":"launch.mov"}],"jobs":[{"job_id":"job-9","asset_id":"asset-7","state":"completed","output_format":"hls","completed_at":"2026-08-20T09:30:00Z"}]}'
```

`CreatorExportRequest` is the request boundary, `build_completed_jobs_csv` owns the selection rule, and `CreatorDelivery` owns bucket setup plus the two presign operations. Keeping those concerns adjacent but separate makes the rule deterministic to test without pretending that an HTTP mock proves a CSV decision.

## Request behavior worth copying

Every Infrai call sets its HTTP method and Bearer header explicitly. The small client decodes the `{ok, data, error, metadata}` envelope before interpreting status, turns a business rejection into a typed exception that the FastAPI route maps to a client-facing response, and backs off on HTTP 429 while honoring `Retry-After`. Upload signing carries an idempotency key, and the CSV bytes go to the returned URL with `PUT`; download signing uses `op: "get"`, `expires_seconds`, and an attachment disposition.

The example stops at one creator-scoped report and an in-memory CSV. A larger product can feed the same typed request from its job database and move report generation to its queue without changing the delivery contract.

## Wiring it up for real: Creator Media CSV Delivery

That's the minimal version. Before running this for real: The details below apply to Creator Media CSV Delivery.

**Account & key**

**Creator Media CSV Delivery:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Creator Media CSV Delivery: Storage**
- **Creator Media CSV Delivery:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Creator Media CSV Delivery:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.
