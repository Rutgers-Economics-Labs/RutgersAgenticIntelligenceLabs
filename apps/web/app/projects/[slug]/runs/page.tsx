import { Suspense } from "react";
import { RunsClient } from "./client";

export default function RunsPage() {
  return (
    <Suspense>
      <RunsClient />
    </Suspense>
  );
}
