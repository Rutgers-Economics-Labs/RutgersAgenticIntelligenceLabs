with open("packages/web/components/layout/TopBar.tsx", "r") as f:
    content = f.read()

# Replace TopBar to accept projectSlug and pass it to ProjectSwitcher if needed.
# But actually ProjectSwitcher uses `urlProjectId` from `searchParams` and `localStorage`,
# let's change TopBar to accept `projectSlug?: string` and pass it to ProjectSwitcher.

new_content = content.replace("export function TopBar() {", "export function TopBar({ projectSlug }: { projectSlug?: string }) {")
new_content = new_content.replace("<ProjectSwitcher />", "<ProjectSwitcher projectSlug={projectSlug} />")

with open("packages/web/components/layout/TopBar.tsx", "w") as f:
    f.write(new_content)
