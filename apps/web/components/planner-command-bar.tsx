"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { fetchPendingQa } from "@/lib/api";

const SECTION_PROMPTS: Record<string, string> = {
  overview: "Ask the planner what changed, what matters now, or what you should do next.",
  dashboard: "Ask what the data is showing or what to inspect next.",
  planner: "Ask for a queue update, next dispatch, or a new planner action.",
  launch: "Describe the new work package you want the planner to create.",
  sessions: "Ask which runs matter, what got stuck, or what needs review.",
  review: "Ask what should be approved, rejected, or repaired first.",
  sources: "Ask which source to trust, add, or investigate further.",
  artifacts: "Ask which outputs are ready, stale, or need verification.",
  integrity: "Ask what is blocking trusted promotion or what to repair first.",
  ontology: "Ask what data is missing or what hydration should happen next.",
  repo: "Ask where a file lives or what repo path to inspect next.",
  settings: "Ask what configuration is safe to change.",
  zen: "Ask for a calm summary of the project state.",
  agent: "Continue the planner thread directly.",
  skills: "Ask which agent skill matters for the current work.",
};

export function PlannerCommandBar({ slug, section }: { slug: string; section: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const [input, setInput] = useState("");
  const [pendingQuestions, setPendingQuestions] = useState(0);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const rows = await fetchPendingQa(slug);
        if (active) setPendingQuestions(rows.length);
      } catch {
        if (active) setPendingQuestions(0);
      }
    }
    load();
    const interval = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [slug]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const prompt = input.trim();
    if (!prompt) return;
    const params = new URLSearchParams();
    params.set("prompt", prompt);
    params.set("from", pathname || `/projects/${slug}`);
    router.push(`/projects/${slug}/agent?${params.toString()}`);
  }

  return (
    <div className="planner-command-bar">
      <div className="planner-command-copy">
        <div className="rail-label">Prompt Planner</div>
        <div className="mono-muted">Use plain language to update the plan, ask what is next, or request work.</div>
      </div>
      <form className="planner-command-form" onSubmit={handleSubmit}>
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          className="planner-command-input"
          placeholder={SECTION_PROMPTS[section] ?? SECTION_PROMPTS.overview}
        />
        <button type="submit" className="planner-command-submit">
          Send
        </button>
      </form>
      <div className="planner-command-links">
        <Link href={`/projects/${slug}/planner`} className="planner-command-link">
          Board
        </Link>
        <Link href={`/projects/${slug}/agent`} className="planner-command-link">
          Thread
        </Link>
        <Link href={`/projects/${slug}/review`} className="planner-command-link">
          Review
        </Link>
        <Link href={`/projects/${slug}/agent?panel=inbox`} className="planner-command-link">
          Inbox{pendingQuestions > 0 ? ` ${pendingQuestions}` : ""}
        </Link>
      </div>
    </div>
  );
}
