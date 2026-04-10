const fs = require("fs");

let content = fs.readFileSync("packages/web/convex/projectChats.ts", "utf-8");

content = content.replace(
  `    } else if (args.projectSlug) {
      project = await ctx.db.query("projects").withIndex("by_slug", (q) => q.eq("slug", args.projectSlug)).first();
    }`,
  `    } else if (args.projectSlug) {
      project = await ctx.db.query("projects").withIndex("by_slug", (q) => q.eq("slug", args.projectSlug as string)).first();
    }`
);

fs.writeFileSync("packages/web/convex/projectChats.ts", content);
