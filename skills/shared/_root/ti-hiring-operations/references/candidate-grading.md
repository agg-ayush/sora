# Grading a candidate's assessment session

- Judge the candidate's decision trail from prompts.txt (diagnosis, stakeholder questioning, integrity calls, decider-vs-executor discipline, approval gates, eval demands, time use). Ignore the code the agent produced: the assessment tests the candidate's judgment, not the agent's output. Don't spend calls re-running or reviewing their scripts unless explicitly asked.
- Structure the verdict as: what they did correctly, what they did poorly, bottom line. Cite prompt numbers as evidence for each point.
- Separate candidate-side concerns from eval-tooling issues; never penalize a candidate for a pipeline artifact.

## Coaching a candidate / mock interview (read-only help)

When helping someone prep for the follow-up interview on their own session:

1. Ground explanations in the actual assignment files (`/home/ubuntu/ti-hiring-assignments/<slug>/assignment.md`, `briefs/`, `starter/`) before explaining the problem; don't paraphrase from memory.
2. Build mock questions from the grading areas above (decision trail, stakeholder conflicts, prioritisation, what they skipped and why, time use), anchored to their specific prompt numbers. Do not invent deep technical edge-case drills (exact loader behaviour on include cycles etc.) as "what they'll ask": the interview probes judgment, so check this file before claiming interviewer depth.
3. Run the mock one question at a time: ask, wait for their answer, judge it (score, what was right, what was missed, a short model answer they can say aloud), then the next question.
4. Match the candidate's register (e.g. Hinglish) and keep it simple: short sentences, one analogy max, no stacked jargon. If they say they didn't understand, rewrite in a few plain lines rather than re-sending the same structure. Validate analogies they offer by saying what's right and correcting only the off parts.
5. Stay inside read-only scope: answering, explaining and mock practice are fine; no writes, shares or grants on their behalf.
