import { KrailPreview } from "@/components/krail/krail-preview";
import { mockKrailPreviewAdapter } from "@/lib/krail/mock-adapter";

export default async function KrailPreviewPage() {
  const model = await mockKrailPreviewAdapter.getPreview();
  return <KrailPreview model={model} />;
}
