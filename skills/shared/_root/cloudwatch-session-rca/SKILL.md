---
name: cloudwatch-session-rca
description: Use when investigating session failures in CloudWatch logs.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [aws, cloudwatch, incident, rca]
---

# CloudWatch session RCA

## When to Use

Use for read-only, timestamp-grounded investigations of session incidents in a CloudWatch log group.

## Workflow

- Confirm account/profile/region with `aws --profile PROFILE --region REGION sts get-caller-identity` before querying. Convert requested UTC bounds to epoch milliseconds; `--end-time` is exclusive.
- For structured session logs, filter with `{ $.sessionId = "EXACT_ID" }`; preserve the source token verbatim. Use `aws logs filter-log-events --log-group-name GROUP --start-time MS --end-time MS --filter-pattern PATTERN --output json --page-size 1000` without `--no-paginate` or `--max-items`. AWS CLI auto-pagination merges pages; validate raw event counts and unique `eventId`s, especially for >1000 events.
- Save the complete CLI JSON per session before summarizing. Keep `eventId`, CloudWatch `timestamp`, and raw `message` so each excerpt can be checked. Do not mistake the first observed polling error for the polling-start time, particularly with a bounded query.
- Search both literal error tokens and observed natural-language log messages. A literal `"media_gate_fail_open"` may miss `media gate fail-open fired`; `%fail.open%` catches the latter. A case-insensitive webhook substring pattern is `%[Ww][Ee][Bb][Hh][Oo][Oo][Kk]%` when supported by the filter parser.
- Distinguish warning/fail-open signals from state transitions: compare poll errors, gate events, `entered rejected`, ready-TTL expiry, teardown, and subsequent endpoint outcomes in timestamp order. A fail-open log alone does not prove the media gate was satisfied.
- A zero-match webhook or phone query in one log group/window means only that no matching log line was observed there. Do not infer an upstream webhook was never emitted or received without other telemetry. Keep investigation read-only; put downloaded artifacts in scratch, not a production repository.
- For media-gate expiry, reconcile the session detail's append-only events (including `ready_expired` detail, platform-stamped participant webhooks, screenshare IDs, and the last `media_gate_recording_poll` before expiry) with structured CloudWatch rejection reason and the Recall bot's status/recording/participant-event artifacts. Preserve **both** `phoneGate` and `mediaGate` when redacting `ready_expired` details; an accidentally empty `{}` projection can hide a real `mediaGate:true` rejection. `phoneJoin` is a seen-once display signal, not proof of a currently connected phone camera. A completed recording after teardown does not establish recording availability at the gate read; a successful `in_call_recording` poll just before expiry does. Redact names, email, token, webhook IDs, and signed download URLs from saved projections.
- Compare the ECS task-definition image commit with local checkout before using source to explain gate behavior; deployment may differ on phone-confirmation latching. When a mobile camera historically overlapped a single screenshare yet expiry still shows `phoneGate`, check for the durable confirmation flag/event, and say when historic projection/gate-read state is unavailable rather than asserting a cause beyond observed refusal.
- Reconstruct `participant_media_state` from all ingested participant events by `(participantId, signal)` using the provider's `detail_json.at` and webhook-id ordering, not just `screenshare_on` events. `candidate_left_meet` projects `screenshare:disconnected` for **every** departing participant, creating a screenshare row even for someone who never shared. The phone matcher counts *all* screenshare rows regardless of state, so a phantom row from an unrelated leave plus a genuine screenshare row makes the laptop identity ambiguous and hard-blocks phone despite a delivered mobile webcam-on. Corroborate this mechanism with Recall's participant-event artifact and `ready_expired {"phoneGate":true}`; no read-pacer outage need be involved.
- In a cohort-level Recall verification, include `ready_expired_teardown_incomplete` rows as gate expiries: teardown is a subsequent cleanup outcome. Classify against the actual refusal time (or explicitly say when only later `ready_expired` audit time is available). A phone that was on earlier but left before refusal is not proof it was on at refusal; call out the earlier possible false-negative separately. If a bot has no recording and thus no participant-event artifact, absence of observed participant webhooks is **UNKNOWN**, not proof of no phone join. Distinguish `mediaGate:true` (ordinary gate/read failure) from `phoneGate:true` when identifying the immediate blocker; a live mobile camera alongside `mediaGate:true` does not prove the phone predicate caused that refusal.
