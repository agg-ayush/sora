# Secrets Rotation — LLM Gateway Key (TFY) and Shared Credentials

> **Owns:** where the shared LLM gateway key (`TFY_API_KEY`, TrueFoundry `https://<llm-gateway>`, header `x-tfy-api-key`) is stored across every environment, and the exact steps to rotate it. This covers the alpha-learn-content-gen system. **Not here:** fleet bring-up or app architecture.

## What it does (one line)

Every LLM call in the system (Claude, Gemini TTS, ElevenLabs alignment) rides one TrueFoundry gateway credential; this runbook is the authoritative list of every place that key is stored and how to rotate it without leaving a stale copy behind.

## Why one runbook

The same `TFY_API_KEY` is read at runtime by the QC dashboard, the agent-supervisor, the article-generation and script-generation Windows fleets, and GitHub Actions CI. Rotating it in only one place (e.g. the QC dashboard) leaves the fleets on the old key and they start returning `401 Unauthorized: Forbidden: Invalid token`. Rotating means updating **every store below**, then **restarting the processes** that hold the old value in memory.

## Where the key lives (the complete inventory)

| Location | Store | How it's provisioned | Picked up |
|---|---|---|---|
| Local dev (Ayush's Mac) | `~/.zshrc` (`export TFY_API_KEY=…`) | manual | new shells / re-source |
| QC dashboard — **Linux** host | `/home/ubuntu/.env` on the Lightsail box | manual edit | passed via `--env-file` — **baked into the container at `docker run`; `docker restart` does NOT re-read it — recreate the container** |
| QC dashboard — **Windows** staging host | SSM SecureString `/alpha-learn/qc-dashboard/TFY_API_KEY` (ap-south-1) | `aws ssm put-parameter --overwrite` | at service start — restart the qc-dashboard / agent-supervisor services |
| **Article-generation + script-generation fleets** (Windows, us-east-1) | SSM SecureString `/alpha-gen/TFY_API_KEY` (us-east-1) — **one param covers both fleets** | `aws ssm put-parameter --overwrite` (canonical tool: `scripts/sync_env_to_ssm.py --overwrite` in the content repo) | hydrated per worker-process start by the bootstrap's `hydrate_from_ssm()` — restart the worker scheduled task on each running box |
| **GitHub Actions CI** (qc-dataset-analyzer, feedback-improvement, qc-self-healer, golden-fixer, golden-build) | repo secret `TFY_API_KEY` (actions app) | `gh secret set TFY_API_KEY` | next workflow run |
| **Render fleet** (eu-north-1) | — | **N/A — no TFY.** The render worker is pure PPTX→MP4 COM, no LLM calls; eu-north-1 SSM has no TFY params | nothing |

**Notes**
- `TFY_BASE_URL` is a static URL and does not rotate with the key.
- The golden AMIs contain **no** secrets — hydration is at boot/process-start from SSM, so rotation needs **no AMI rebake**.
- AWS Secrets Manager holds no TFY secrets in any region — SSM Parameter Store is the only AWS store in play.
- Gotcha: `ppt-generator/src/llm_call_utils.py` calls `load_dotenv()`, so a hand-dropped `.env` in a worker's checkout (`C:\article-gen-worker\alpha-learn-content-gen\` / the script-gen equivalent) would **shadow SSM** — if a box still 401s after the SSM update, check for that file.

## Rotation procedure

1. Get the new key from TrueFoundry.
2. Verify it authenticates before propagating (a 200 here means the key is valid):
   `curl -s -o /dev/null -w '%{http_code}' -H "x-tfy-api-key: <new>" https://<llm-gateway>/api/llm/api/inference/openai/models`
3. Update every store in the table above.
4. Restart the processes that hold the old key in memory:
   - QC Linux box: recreate the `qc-dashboard` container (restart does not re-read `.env`); same URL/DNS, no mapping changes. **Also recreate `agent-supervisor`** — on the supervised arch it is a *separate* container that reads the same `.env`, and new agent sessions spawn through it, so a stale supervisor key 401s even when the dashboard is updated. Both containers must be recreated.
   - QC Windows host: restart the qc-dashboard + agent-supervisor services.
   - Generation fleets: `Stop-ScheduledTask` / `Start-ScheduledTask` the worker task on each running baseline + live clone via SSM Run Command (no reboot, no ASG change). Burst clones launched later self-heal.
   - CI: nothing — next run picks it up.
5. Verify each environment authenticates (dashboard `/api/healthz` + a real LLM-backed run; worker logs show `loaded N parameter(s) from /alpha-gen/` with no 401/Invalid token).

## Related

- Content repo: `docs/infra/fleets.md` + the per-fleet runbooks under `docs/infra/`.
