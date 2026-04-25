import clsx from "clsx";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type MarkdownRendererProps = {
  content: string;
  className?: string;
};

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  return (
    <div className={clsx("prose-rail", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ className: linkClassName, ...props }) => (
            <a
              className={clsx(
                "underline decoration-[var(--accent)] decoration-2 underline-offset-4 transition-colors hover:text-[var(--accent)]",
                linkClassName
              )}
              {...props}
            />
          ),
          code: ({ className: codeClassName, children, ...props }) => (
            <code className={clsx(codeClassName)} {...props}>{children}</code>
          ),
          pre: ({ className: preClassName, ...props }) => (
            <pre className={clsx(preClassName)} {...props} />
          ),
          table: ({ className: tableClassName, ...props }) => (
            <div className="overflow-x-auto">
              <table className={clsx("w-full border-collapse", tableClassName)} {...props} />
            </div>
          )
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
