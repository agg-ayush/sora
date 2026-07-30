# holo — launch an in-role orchestrator session with the right tier skill.
# Add to ~/.zshrc (or ~/.bashrc).
#
#   holo 1      # Tier-1 sub-orchestrator (per-repo) — default
#   holo 2      # Tier-2 supervisor (per-issue)
#   holo dash   # web dashboard (tier task visibility at localhost:9119)
#   holo        # Tier-1 (default, same as 'holo 1')
#   holo -p x   # Tier-1 pinned to a per-repo profile
#   holo 2 -q "issue ..."  # Tier-2 one-shot
holo() {
  case "$1" in
    1) shift; hermes -s tier1-suborchestration "$@" ;;
    2) shift; hermes -s tier2-orchestration "$@" ;;
    dash) shift; hermes dashboard "$@" ;;
    *) hermes -s tier1-suborchestration "$@" ;;
  esac
}
