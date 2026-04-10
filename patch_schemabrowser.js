const fs = require("fs");

let content = fs.readFileSync("packages/web/components/analysis/SchemaBrowser.tsx", "utf-8");

content = content.replace(
  `const [schema, setSchema] = useState<Record<string, { name: string; type: string }[]>>({});`,
  `const [schema, setSchema] = useState<Record<string, { columns: { name: string; type: string; density?: number }[]; row_count?: number }>>({});`
);

content = content.replace(
  `            {filteredTables.map(([tableName, columns]) => (`,
  `            {filteredTables.map(([tableName, tableData]) => {
              const columns = tableData.columns || [];
              const rowCount = tableData.row_count || 0;
              return (`
);

content = content.replace(
  `                  <span className="ml-auto text-[10px] font-mono tabular-nums opacity-0 group-hover:opacity-40 transition-opacity">
                    {columns.length}
                  </span>`,
  `                  <span className={cn(
                    "ml-auto text-[10px] font-mono tabular-nums px-1.5 py-0.5 rounded",
                    rowCount > 0 ? "bg-green-500/10 text-green-500" : "opacity-0 group-hover:opacity-40 transition-opacity bg-[--muted]/50"
                  )}>
                    {rowCount > 0 ? \`\${rowCount} rows\` : \`\${columns.length} cols\`}
                  </span>`
);

content = content.replace(
  `                        <span className="text-[9px] font-black text-[--muted-foreground]/20 uppercase tracking-tighter shrink-0 border border-[--border] px-1.5 rounded bg-[--muted]/5">
                          {col.type}
                        </span>`,
  `                        <div className="flex items-center gap-2">
                          {col.density !== undefined && rowCount > 0 && (
                            <div className="w-16 h-1.5 bg-[--muted] rounded-full overflow-hidden" title={\`Density: \${(col.density * 100).toFixed(1)}%\`}>
                              <div className={cn("h-full", col.density > 0.8 ? "bg-green-500" : col.density > 0.3 ? "bg-yellow-500" : "bg-red-500")} style={{ width: \`\${col.density * 100}%\` }} />
                            </div>
                          )}
                          <span className="text-[9px] font-black text-[--muted-foreground]/20 uppercase tracking-tighter shrink-0 border border-[--border] px-1.5 rounded bg-[--muted]/5">
                            {col.type}
                          </span>
                        </div>`
);

content = content.replace(
  `              </div>
            ))}
          </div>`,
  `              </div>
            )}
            )}
          </div>`
);


fs.writeFileSync("packages/web/components/analysis/SchemaBrowser.tsx", content);
