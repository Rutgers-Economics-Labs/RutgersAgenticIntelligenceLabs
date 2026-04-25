import Link from "next/link";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { ProjectShell } from "@/components/project-shell";
import { fetchRepoPath } from "@/lib/api";

// ── Icon helpers ──────────────────────────────────────────────────────

function FileIcon({ ext }: { ext?: string }) {
  const e = (ext ?? "").toLowerCase();
  if (["md", "mdx", "markdown"].includes(e)) return <span style={{ color: "var(--s-review)" }}>⬜</span>;
  if (["yaml", "yml"].includes(e)) return <span style={{ color: "var(--s-awaiting)" }}>⬜</span>;
  if (["py"].includes(e)) return <span style={{ color: "var(--s-running)" }}>⬜</span>;
  if (["json", "ndjson"].includes(e)) return <span style={{ color: "var(--muted)" }}>⬜</span>;
  return <span style={{ color: "var(--border-strong)", opacity: 0.3 }}>⬜</span>;
}

const QUICK_PATHS = [
  { label: "rail.yaml",           path: "rail.yaml" },
  { label: "research_plan/",      path: "research_plan" },
  { label: "agents/",             path: "agents" },
  { label: "scripts/",            path: "scripts" },
  { label: ".ontology/",          path: ".ontology" },
  { label: "artifacts/",          path: "artifacts" },
];

function EntryRow({ slug, entry }: { slug: string; entry: any }) {
  const ext = entry.name.includes(".") ? entry.name.split(".").pop() : undefined;
  const isDir = entry.kind === "directory";
  return (
    <Link
      href={`/projects/${slug}/repo?path=${encodeURIComponent(entry.path)}`}
      style={{ display: "block" }}
    >
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "7px 14px",
        borderBottom: "1px solid var(--border)",
        transition: "background 100ms",
        fontFamily: "JetBrains Mono, monospace",
        fontSize: 12,
        color: "var(--fg)",
      }}>
        <span style={{ fontSize: 8, opacity: 0.5 }}>
          {isDir ? "▶" : "·"}
        </span>
        {!isDir && <FileIcon ext={ext} />}
        <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {entry.name}{isDir ? "/" : ""}
        </span>
        {entry.sizeBytes != null && !isDir && (
          <span style={{ fontSize: 10, color: "var(--muted)" }}>
            {entry.sizeBytes < 1024 ? `${entry.sizeBytes}B` : `${(entry.sizeBytes / 1024).toFixed(1)}K`}
          </span>
        )}
        <span style={{ fontSize: 10, color: "var(--muted)", marginLeft: 4 }}>
          {entry.kind}
        </span>
      </div>
    </Link>
  );
}

// ── Right rail: quick links + breadcrumb ─────────────────────────────

function RepoRightRail({ slug, selectedPath }: { slug: string; selectedPath: string }) {
  const segments = selectedPath.split("/").filter(Boolean);
  return (
    <div>
      <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)" }}>
        <span className="rail-label">Quick Links</span>
      </div>
      {QUICK_PATHS.map(({ label, path }) => {
        const active = selectedPath === path;
        return (
          <Link
            key={path}
            href={`/projects/${slug}/repo?path=${encodeURIComponent(path)}`}
            style={{ display: "block" }}
          >
            <div style={{
              padding: "8px 14px",
              borderBottom: "1px solid var(--border)",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 11,
              background: active ? "var(--fg)" : "transparent",
              color: active ? "var(--bg)" : "var(--fg)",
              transition: "background 100ms",
            }}>
              {label}
            </div>
          </Link>
        );
      })}

      {/* Breadcrumb */}
      {segments.length > 0 && (
        <>
          <div style={{ padding: "8px 14px", borderTop: "1px solid var(--border)", marginTop: 8 }}>
            <span className="rail-label">Path</span>
          </div>
          <div style={{ padding: "6px 14px 10px", display: "flex", flexWrap: "wrap", gap: 4 }}>
            <Link href={`/projects/${slug}/repo?path=research_plan`}>
              <span style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                color: "var(--accent)",
                cursor: "pointer",
              }}>root</span>
            </Link>
            {segments.map((seg, i) => {
              const partial = segments.slice(0, i + 1).join("/");
              return (
                <span key={i} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <span style={{ color: "var(--muted)", fontSize: 10 }}>/</span>
                  <Link href={`/projects/${slug}/repo?path=${encodeURIComponent(partial)}`}>
                    <span style={{
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 10,
                      color: i === segments.length - 1 ? "var(--fg)" : "var(--accent)",
                    }}>{seg}</span>
                  </Link>
                </span>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────

export default async function RepoPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ path?: string }>;
}) {
  const { slug } = await params;
  const { path } = await searchParams;
  const selectedPath = (path ?? "research_plan").replace(/^\/+/, "");

  let repoNode: any = null;
  let fetchError: string | null = null;

  try {
    repoNode = await fetchRepoPath(slug, selectedPath);
  } catch {
    try {
      repoNode = await fetchRepoPath(slug, "research_plan");
      fetchError = `Path \`${selectedPath}\` not found — showing research_plan/`;
    } catch {
      fetchError = `Could not read repo for project "${slug}".`;
    }
  }

  const ext = repoNode?.kind === "file"
    ? (repoNode.extension ?? repoNode.path?.split(".").pop() ?? "")
    : "";
  const isMarkdown = ["md", "mdx", "markdown"].includes(ext.toLowerCase());
  const isYaml = ["yaml", "yml"].includes(ext.toLowerCase());
  const isCode = ["py", "ts", "tsx", "js", "json", "sh", "toml", "ini", "ndjson"].includes(ext.toLowerCase());

  return (
    <ProjectShell
      slug={slug}
      title="Repo"
      section="repo"
      rightRail={<RepoRightRail slug={slug} selectedPath={selectedPath} />}
    >
      {fetchError && (
        <div style={{
          padding: "8px 16px",
          borderBottom: "1px solid var(--border)",
          background: "var(--panel-alt)",
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 11,
          color: "var(--s-awaiting)",
        }}>
          {fetchError}
        </div>
      )}

      {!repoNode ? (
        <div style={{
          padding: "40px 16px",
          textAlign: "center",
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 12,
          color: "var(--muted)",
        }}>
          Unable to load repo. Is the project configured with a localRepoPath?
        </div>
      ) : repoNode.kind === "directory" ? (
        <div>
          {/* Dir header */}
          <div style={{
            padding: "8px 14px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}>
            <span className="rail-label">{repoNode.path || selectedPath}/</span>
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
              {(repoNode.entries ?? []).length} entries
            </span>
          </div>

          {(repoNode.entries ?? []).length === 0 ? (
            <div style={{ padding: "24px 14px", color: "var(--muted)", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
              Empty directory.
            </div>
          ) : (
            (repoNode.entries as any[]).map((entry: any) => (
              <EntryRow key={entry.path} slug={slug} entry={entry} />
            ))
          )}
        </div>
      ) : (
        <div>
          {/* File header */}
          <div style={{
            padding: "8px 14px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}>
            <span className="rail-label" style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
              {repoNode.path}
            </span>
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
              {ext || "text"}
            </span>
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--muted)" }}>
              {repoNode.sizeBytes != null
                ? repoNode.sizeBytes < 1024
                  ? `${repoNode.sizeBytes}B`
                  : `${(repoNode.sizeBytes / 1024).toFixed(1)}K`
                : ""}
            </span>
          </div>

          {/* Content */}
          {isMarkdown ? (
            <div style={{ padding: "20px 24px" }}>
              <MarkdownRenderer content={repoNode.content ?? ""} />
            </div>
          ) : isYaml || isCode ? (
            <pre style={{
              margin: 0,
              padding: "16px",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 11,
              lineHeight: 1.7,
              color: "var(--fg)",
              background: "var(--panel-alt)",
              overflowX: "auto",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}>
              {repoNode.content ?? ""}
            </pre>
          ) : (
            <pre style={{
              margin: 0,
              padding: "16px",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 11,
              lineHeight: 1.7,
              color: "var(--muted)",
              overflowX: "auto",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}>
              {repoNode.content ?? "(binary or unsupported format)"}
            </pre>
          )}
        </div>
      )}
    </ProjectShell>
  );
}
