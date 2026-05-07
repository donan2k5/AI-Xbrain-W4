# Backend

FastAPI service for L1-L2 RAG over an existing Amazon Bedrock Knowledge Base.

L1-L2 requests are stateless. `session_id` is accepted only as an optional field for future L4 memory work.

## Run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# edit .env with AWS_REGION, BEDROCK_KB_ID, BEDROCK_MODEL_ID
# optionally set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN
uvicorn app.main:app --reload --port 8001
```

The app reads AWS credentials from `.env` when `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are set. If they are blank, boto3 falls back to the normal AWS credential chain.

If your machine has `HTTP_PROXY` or `HTTPS_PROXY` set to a dead local proxy, use `..\scripts\start-local.ps1` from the repo root. The script clears proxy env vars for the backend process and writes logs to `logs/backend.txt`.

## Endpoints

- `POST /api/chat`
- `GET /api/traces/{trace_id}`
- `GET /api/health`
