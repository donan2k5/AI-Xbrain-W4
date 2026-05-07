# AI-XBrain RAG L1-L2

Local-first React + FastAPI app for Week 4 L1-L2 RAG demo.

## What It Does

- Left rail hardcodes L1/L2 demo questions.
- Clicking a question fills the chat input.
- Press Enter to send the question.
- Backend retrieves from an existing Amazon Bedrock Knowledge Base and generates with a Bedrock model.
- Each assistant response has a small `Trace` button.
- Trace opens the right panel with sources, raw chunks, retrieval config, model info, and logs.
- Phase L1-L2 does not use session memory; every request is independent.

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env:
# AWS_REGION=...
# BEDROCK_KB_ID=...
# BEDROCK_MODEL_ID=...
# AWS_ACCESS_KEY_ID=...
# AWS_SECRET_ACCESS_KEY=...
# AWS_SESSION_TOKEN=... # only if using temporary credentials
uvicorn app.main:app --reload --port 8001
```

AWS credentials can live in `backend/.env`. If `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are empty, boto3 falls back to your AWS CLI profile or default credential chain.

Default model ID is `us.anthropic.claude-sonnet-4-20250514-v1:0`, the US inference profile for Claude Sonnet 4. Enable Claude Sonnet 4 in Amazon Bedrock Model access for the same region as the Knowledge Base.

## Run With Logs

Use the local scripts when you want nohup-style background processes with tail-able logs:

```powershell
.\scripts\stop-local.ps1
.\scripts\start-local.ps1
.\scripts\tail-logs.ps1 backend
```

Log files:

- `logs/backend.txt`
- `logs/frontend.txt`

The backend start script clears `HTTP_PROXY` and `HTTPS_PROXY` for the backend process because a bad local proxy such as `http://127.0.0.1:9` breaks boto3/Bedrock calls.

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

If the backend runs on another port:

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8001"
npm run dev
```

## Phase Boundary

This phase intentionally implements L1-L2 only. L3 tools and L4 memory can be added later by extending the trace model with `tool_calls` and `context_window`.
