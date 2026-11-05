# Concept-demo mockups (shown live by the user)

- "Mockup" doesn't automatically mean barebones. If the user wants a demo-quality concept, build a proper good-looking multi-page UI with the design skills (ui-ux-pro-max, frontend-design, impeccable) and tell the build agent to use them. Plain wireframe styling is only for throwaway sketches.
- The UI must not explain or market its own features: no legends, no "how this works" copy, no feature callouts. The user narrates the demo. The UI should look like the real product in use.
- Back the UI with a realistic mock record (ticket number, parties, terms, review notes, redline rounds, people) so it reads as a real case, not a feature tour.
- Serve previews on 127.0.0.1 only. The user connects over an SSH tunnel. Never bind to a public IP.
- When pushing a mockup to a new repo, push only the mockup files with fresh history. Don't push a fork of the source repo.
- Build it through claude_orchestrate with Opus (no T1/T2 flow for mockups). A new workdir triggers Claude Code's folder-trust dialog, which can kill the orchestrate session at startup. Pre-trust the dir in a throwaway tmux claude session (select "Yes, I trust this folder"), then start the orchestrate run.
