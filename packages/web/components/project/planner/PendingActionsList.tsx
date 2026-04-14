"use client";

import { useMutation, useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { Id } from "@/convex/_generated/dataModel";
import { AlertCircle, Check, X, ShieldAlert, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface PendingActionsListProps {
  projectId: Id<"projects">;
}

export function PendingActionsList({ projectId }: PendingActionsListProps) {
  const approvals = useQuery(api.approvals.listByProject, { projectId });
  const resolveApproval = useMutation(api.approvals.resolve);

  if (!approvals) {
    return (
      <div className="flex items-center justify-center p-8 opacity-40">
        <Loader2 className="animate-spin" size={20} />
      </div>
    );
  }

  const pendingApprovals = approvals.filter(a => a.status === "pending");

  const handleResolve = async (id: Id<"approvals">, status: "granted" | "denied") => {
    try {
      await resolveApproval({ approvalId: id, status });
      toast.success(status === "granted" ? "Action Approved" : "Action Denied");
    } catch (err) {
      toast.error("Failed to resolve approval");
    }
  };

  if (pendingApprovals.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center space-y-3 opacity-30 animate-in fade-in duration-700">
        <div className="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center">
            <Check size={24} className="text-green-500" />
        </div>
        <div>
            <p className="text-[10px] font-black uppercase tracking-widest">Everything Clear</p>
            <p className="text-[9px] mt-1 max-w-[150px]">No pending approvals or blocker questions at this moment.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      <h3 className="text-[9px] font-black uppercase tracking-[0.2em] text-[--muted-foreground] opacity-60">Pending Approvals</h3>
      
      <div className="space-y-3">
        {pendingApprovals.map((approval) => (
          <div 
            key={approval._id} 
            className="p-3 rounded-xl border border-white/5 bg-white/2 hover:bg-white/5 transition-all group"
          >
            <div className="flex items-start gap-3">
              <div className="mt-0.5 shrink-0 text-yellow-500/80">
                <ShieldAlert size={16} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-bold truncate">
                    {approval.approvalType.replace(/_/g, " ")}
                  </p>
                  <span className="text-[8px] font-black uppercase tracking-tighter bg-yellow-500/10 text-yellow-500/80 px-1.5 py-0.5 rounded border border-yellow-500/20">
                    Gate
                  </span>
                </div>
                <p className="text-[10px] text-[--muted-foreground] mt-1 leading-relaxed">
                  Requested by <span className="text-[--foreground] font-medium uppercase tracking-tighter">{approval.requestedByRole}</span> agent to proceed with task execution.
                </p>
                
                <div className="flex gap-2 mt-3">
                  <button 
                    onClick={() => handleResolve(approval._id, "granted")}
                    className="flex-1 h-8 rounded-lg bg-green-500/20 border border-green-500/30 text-green-400 text-[10px] font-black uppercase tracking-widest hover:bg-green-500/30 transition-all flex items-center justify-center gap-1.5"
                  >
                    <Check size={12} />
                    Approve
                  </button>
                  <button 
                    onClick={() => handleResolve(approval._id, "denied")}
                    className="flex-1 h-8 rounded-lg bg-red-500/20 border border-red-500/30 text-red-400 text-[10px] font-black uppercase tracking-widest hover:bg-red-500/30 transition-all flex items-center justify-center gap-1.5"
                  >
                    <X size={12} />
                    Deny
                  </button>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="pt-4 flex items-center gap-2">
         <AlertCircle size={10} className="text-[--muted-foreground] opacity-40" />
         <p className="text-[9px] text-[--muted-foreground] opacity-40 leading-tight">
           Approval grants the agent permission to modify files, trigger API calls, or run hydration steps.
         </p>
      </div>
    </div>
  );
}
