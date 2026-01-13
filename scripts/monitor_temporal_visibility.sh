#!/usr/bin/env bash
set -euo pipefail

ADDRESS="${TEMPORAL_ADDRESS:-${TEMPORAL_VISIBILITY_ADDRESS:-localhost:7233}}"
NAMESPACE="${TEMPORAL_NAMESPACE:-${TEMPORAL_VISIBILITY_NAMESPACE:-default}}"
WORKFLOW_TYPE="${TEMPORAL_WORKFLOW_TYPE:-EpisodeIngestionVisibilityWorkflow}"
QUERY="${TEMPORAL_QUERY:-WorkflowType='${WORKFLOW_TYPE}'}"

if ! command -v temporal >/dev/null 2>&1; then
  echo "temporal CLI not found. Install it or run via devcontainer/host."
  exit 1
fi

echo "Temporal address: ${ADDRESS}"
echo "Temporal namespace: ${NAMESPACE}"
echo "Query: ${QUERY}"
echo

temporal workflow list --address "${ADDRESS}" --namespace "${NAMESPACE}" --query "${QUERY}"
