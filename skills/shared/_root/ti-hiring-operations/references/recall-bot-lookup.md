# Querying Recall bots directly

- The local `RECALL_API_KEY` env var on the box is NOT the orchestrator's key and returns 401 `authentication_failed` against the orchestrator's region. Use the orchestrator key from SSM without printing it: `aws --profile trilogy --region ap-south-1 ssm get-parameter --name /ti/orchestrator/RECALL_API_KEY --with-decryption --query Parameter.Value --output text`.
- Region host is `https://ap-northeast-1.recall.ai` (from the task def env `RECALL_API_URL`). Endpoint: `GET /api/v1/bot/<bot_id>/`.
- Bot state lives in `status_changes[]` (code, sub_code, created_at); top-level `status` is null.
- Bots are configured `start_recording_on: participant_join`, so a bot stuck in `in_call_not_recording` for the whole slot is independent proof the candidate never joined the Meet.
