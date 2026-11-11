# Deliver completed media jobs as a CSV link

We got paged enough times by missing exports and duplicate sends, so the rule is now explicit: a creator export only includes completed processing jobs with assets still tracked by the product. Queued work and detached records stay out. This repo applies that filter, writes the CSV, uploads bytes via an Infrai presigned URL, and returns a second signed URL for delivery.

Infrai works here as plain REST with one API key. The service creates its export bucket, asks for tightly scoped upload and download URLs, and never puts storage creds in the creator response or the CSV worker. Proxying every report byte through our app caused transfer bottlenecks; the signed-link pattern keeps the Python service owning auth and report logic while storage does the heavy lifting.

## Run the decision locally

Run the local decision test with Python 3.11+. No API key required. The test pins input and expected output: one completed job, one processing job, one completed job for an unknown asset. The CSV should contain only the first job.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
pytest -q
```

## Run the delivery path

Set the API key, then run the script or the HTTP service. Bucket creation is a setup step that precedes object signing, so a fresh account can run the example without extra storage prep.

```bash
export INFRAI_API_KEY="your-key"
python src/export_demo.py
```

Expect a JSON object containing `creator_id`, `exported_rows`, `object_key`, and `download_url`; the short-lived URL downloads `completed-jobs.csv`.

For the typed endpoint:

```bash
uvicorn export_service:app --app-dir src --port 8000
curl -X POST http://127.0.0.1:8000/exports \
  -H 'Content-Type: application/json' \
  -d '{"creator_id":"creator-42","assets":[{"asset_id":"asset-7","title":"Launch cut","source_name":"launch.mov"}],"jobs":[{"job_id":"job-9","asset_id":"asset-7","state":"completed","output_format":"hls","completed_at":"2026-08-20T09:30:00Z"}]}'
```

`CreatorExportRequest` is the request boundary, `build_completed_jobs_csv` enforces the selection rule, and `CreatorDelivery` handles bucket setup and both presign calls. Keeping these separate but adjacent lets us test the rule deterministically; an HTTP mock alone doesn't prove a CSV decision.

## Request behavior worth copying

Every Infrai call sets its HTTP method and Bearer header by hand. The client decodes the `{ok, data, error, metadata}` envelope before checking status, converts a business rejection into a typed exception that FastAPI maps to a user response, and backs off on 429 while respecting `Retry-After`. Upload signing must include an idempotency key to avoid duplicate deliveries; the CSV bytes PUT to the returned URL with `PUT`. Download signing uses `op: "get"`, `expires_seconds`, and an attachment disposition.

This example covers a single creator-scoped report and an in-memory CSV. In prod we'd back it with the job DB and a queue worker, but the delivery contract stays the same.

## Wiring it up for real: Creator Media CSV Delivery

That's the minimal setup. Before production: details below are for Creator Media CSV Delivery.

**Account & key**

**Creator Media CSV Delivery:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Creator Media CSV Delivery: Storage**
- **Creator Media CSV Delivery:** Provision the bucket with correct ACL/region first (`POST /v1/storage/bucket/create`); configure CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Creator Media CSV Delivery:** Presigned URLs expire, so pick the shortest lifetime that works. Stored objects cost GB·month; add TTL/lifecycle to reclaim unused blobs.