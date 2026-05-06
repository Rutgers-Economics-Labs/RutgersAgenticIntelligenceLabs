const COLORS: Record<string, { bg: string; color: string; border: string }> = {
  running:          { bg: "color-mix(in srgb, var(--s-running) 12%, transparent)", color: "var(--s-running)",  border: "color-mix(in srgb, var(--s-running) 35%, transparent)" },
  awaiting_approval:{ bg: "color-mix(in srgb, var(--s-awaiting) 12%, transparent)", color: "var(--s-awaiting)", border: "color-mix(in srgb, var(--s-awaiting) 35%, transparent)" },
  awaiting_input:   { bg: "color-mix(in srgb, var(--s-awaiting) 12%, transparent)", color: "var(--s-awaiting)", border: "color-mix(in srgb, var(--s-awaiting) 35%, transparent)" },
  failed:           { bg: "color-mix(in srgb, var(--s-failed) 12%, transparent)",   color: "var(--s-failed)",   border: "color-mix(in srgb, var(--s-failed) 35%, transparent)"   },
  blocked:          { bg: "color-mix(in srgb, var(--s-blocked) 12%, transparent)",  color: "var(--s-blocked)",  border: "color-mix(in srgb, var(--s-blocked) 35%, transparent)"  },
  review:           { bg: "color-mix(in srgb, var(--s-review) 12%, transparent)",   color: "var(--s-review)",   border: "color-mix(in srgb, var(--s-review) 35%, transparent)"   },
  ready:            { bg: "var(--panel-alt)", color: "var(--fg)",    border: "var(--border)" },
  backlog:          { bg: "transparent",      color: "var(--muted)", border: "var(--border)" },
  completed:        { bg: "transparent",      color: "var(--muted)", border: "var(--border)" },
  done:             { bg: "transparent",      color: "var(--muted)", border: "var(--border)" },
  cancelled:        { bg: "transparent",      color: "var(--muted)", border: "var(--border)" },
  pending:          { bg: "transparent",      color: "var(--muted)", border: "var(--border)" },
  needs_changes:    { bg: "color-mix(in srgb, var(--s-blocked) 10%, transparent)", color: "var(--s-blocked)", border: "color-mix(in srgb, var(--s-blocked) 30%, transparent)" },
  active:           { bg: "color-mix(in srgb, var(--s-running) 12%, transparent)", color: "var(--s-running)",  border: "color-mix(in srgb, var(--s-running) 35%, transparent)" },
  connected:        { bg: "color-mix(in srgb, var(--s-running) 12%, transparent)", color: "var(--s-running)",  border: "color-mix(in srgb, var(--s-running) 35%, transparent)" },
  partial:          { bg: "color-mix(in srgb, var(--s-awaiting) 10%, transparent)", color: "var(--s-awaiting)", border: "color-mix(in srgb, var(--s-awaiting) 30%, transparent)" },
  empty:            { bg: "transparent",      color: "var(--muted)", border: "var(--border)" },
  present:          { bg: "color-mix(in srgb, var(--s-running) 12%, transparent)", color: "var(--s-running)",  border: "color-mix(in srgb, var(--s-running) 35%, transparent)" },
  missing:          { bg: "transparent",      color: "var(--muted)", border: "var(--border)" },
  verified:         { bg: "color-mix(in srgb, var(--s-running) 12%, transparent)", color: "var(--s-running)", border: "color-mix(in srgb, var(--s-running) 35%, transparent)" },
  passed:           { bg: "color-mix(in srgb, var(--s-running) 12%, transparent)", color: "var(--s-running)", border: "color-mix(in srgb, var(--s-running) 35%, transparent)" },
  stale:            { bg: "color-mix(in srgb, var(--s-awaiting) 10%, transparent)", color: "var(--s-awaiting)", border: "color-mix(in srgb, var(--s-awaiting) 30%, transparent)" },
  draft:            { bg: "var(--panel-alt)", color: "var(--fg)", border: "var(--border)" },
  exploratory:      { bg: "transparent", color: "var(--muted)", border: "var(--border)" },
  needs_evidence:   { bg: "color-mix(in srgb, var(--s-blocked) 10%, transparent)", color: "var(--s-blocked)", border: "color-mix(in srgb, var(--s-blocked) 30%, transparent)" },
  partially_verified:{ bg: "color-mix(in srgb, var(--s-review) 12%, transparent)", color: "var(--s-review)", border: "color-mix(in srgb, var(--s-review) 35%, transparent)" },
  unverified:       { bg: "transparent", color: "var(--muted)", border: "var(--border)" },
  validated:        { bg: "color-mix(in srgb, var(--s-running) 12%, transparent)", color: "var(--s-running)", border: "color-mix(in srgb, var(--s-running) 35%, transparent)" },
  candidate:        { bg: "transparent", color: "var(--muted)", border: "var(--border)" },
  rejected:         { bg: "color-mix(in srgb, var(--s-blocked) 10%, transparent)", color: "var(--s-blocked)", border: "color-mix(in srgb, var(--s-blocked) 30%, transparent)" },
  supported:        { bg: "color-mix(in srgb, var(--s-running) 12%, transparent)", color: "var(--s-running)", border: "color-mix(in srgb, var(--s-running) 35%, transparent)" },
  unsupported:      { bg: "color-mix(in srgb, var(--s-blocked) 10%, transparent)", color: "var(--s-blocked)", border: "color-mix(in srgb, var(--s-blocked) 30%, transparent)" },
  info:             { bg: "var(--panel-alt)", color: "var(--fg)", border: "var(--border)" },
};

const FALLBACK = { bg: "transparent", color: "var(--muted)", border: "var(--border)" };

export function StatusPill({ value }: { value: string | null | undefined }) {
  const label = (value ?? "unknown").toLowerCase().replace(/\s+/g, "_");
  const s = COLORS[label] ?? FALLBACK;
  return (
    <span
      className="status-chip"
      style={{ background: s.bg, color: s.color, borderColor: s.border }}
    >
      {label.replaceAll("_", " ")}
    </span>
  );
}
