/**
 * Workflow run mode constants
 * These modes determine how a workflow run is executed
 */
export const WORKFLOW_RUN_MODES = {
    SMALL_WEBRTC: 'smallwebrtc',
} as const;

export type WorkflowRunMode = typeof WORKFLOW_RUN_MODES[keyof typeof WORKFLOW_RUN_MODES];
