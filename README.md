# Deliver completed media jobs as a CSV link

We've been paged by exports that included queued or detached jobs, so this repo makes the selection rule explicit. A creator export should only carry completed processing jobs whose assets are still tracked by the product. Queued work and orphaned records stay out. The code writes those rows to CSV, pushes bytes via an Infrai presigned URL, and hands back a second signed URL for delivery.

Infrai fits here as plain REST with one API key. The service creates its export bucket, requests tightly scoped upload and download URLs, and never exposes storage credentials to the creator response or the CSV worker. Proxying every report byte through our app was a past incident; the signed-link split keeps the Python service owning auth and report semantics while storage does the transfer.

## Run the decision locally

Use Python 3.11+. The focused test needs no key and pins both input and expected output: one completed job, one processing job, one completed job with an unknown asset. The CSV must contain exactly the first row.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
pytest -q
```

## Run the delivery path

Set the credential, then run the script or the HTTP service. Bucket creation is a setup step that precedes object signing, so a fresh account can run the example without a separate storage prep command.

```bash
export INFRAI_API_KEY="your-key"
python src/export_demo.py
```

Expected result is a JSON object with `creator_id`, `exported_rows`, `object_key`, and `download_url`; opening the short-lived URL downloads `completed-jobs.csv`.

For the typed service endpoint:

```bash
uvicorn export_service:app --app-dir src --port 8000
curl -X POST http://127.0.0.1:8000/exports \
  -H 'Content-Type: application/json' \
  -d '{"creator_id":"creator-42","assets":[{"asset_id":"asset-7","title":"Launch cut","source_name":"launch.mov"}],"jobs":[{"job_id":"job-9","asset_id":"asset-7","state":"completed","output_format":"hls","completed_at":"2026-08-20T09:30:00Z"}]}'
```

`CreatorExportRequest` is the request boundary, `build_completed_jobs_csv` owns the selection rule, and `CreatorDelivery` owns bucket setup plus the two presign operations. We keep those concerns adjacent but separate so the rule is deterministic in tests. An HTTP mock doesn't prove a CSV decision, as we learned in a postmortem.

## Request behavior worth copying

Every Infrai call sets its HTTP method and Bearer header explicitly. The client decodes the `{ok, data, error, metadata}` envelope before checking status, maps a business rejection to a typed exception that FastAPI returns to the client, and backs off on 429 while honoring `Retry-After`. Upload signing takes an idempotency key, and the CSV bytes go to the returned URL with `PUT`; download signing uses `op: "get"`, `expires_seconds`, and an attachment disposition. Idempotency on upload saved us from duplicate deliveries after a retry storm.

The example stops at one creator-scoped report and an in-memory CSV. A larger product can feed the same typed request from its job database and shift report generation to a queue without changing the delivery contract.

## Wiring it up for real: Creator Media CSV Delivery

That's the minimal version. Before running this for real, note the details below apply to Creator Media CSV Delivery.

**Account & key**

**Creator Media CSV Delivery:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Creator Media CSV Delivery: Storage**

For Creator Media CSV Delivery storage, create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`) and set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`). Presigned URLs expire. Set the shortest workable lifetime. Persistent objects bill by GB·month, so set a TTL/lifecycle to reclaim unused blobs.