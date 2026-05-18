"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { PlusCircle } from "lucide-react";
import { createOntologyFollowUpTask } from "@/lib/api";

export function CreateOntologyFollowUpTaskButton({
  slug,
  title,
  classification,
}: {
  slug: string;
  title: string;
  classification: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    try {
      await createOntologyFollowUpTask(slug, { title, classification });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      className="command-button"
      type="button"
      disabled={busy}
      onClick={run}
      style={{ display: "inline-flex", alignItems: "center", gap: 6, justifyContent: "center" }}
    >
      <PlusCircle size={14} />
      {busy ? "Creating" : "Create task"}
    </button>
  );
}
