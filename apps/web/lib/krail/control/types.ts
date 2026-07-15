import type { ExecutionCapabilityInventory, Project } from "@/lib/krail/api";

export type ExecutionCapabilities = ExecutionCapabilityInventory;

export type ProjectMutation = { project?: Project; error?: { code?: string; message?: string; requestId?: string } };
