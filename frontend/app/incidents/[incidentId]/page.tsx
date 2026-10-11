import Workbench from "../../../components/Workbench";
export default async function IncidentPage({ params }: { params: Promise<{ incidentId: string }> }) {
  const { incidentId } = await params;
  return <Workbench initialIncidentId={incidentId} />;
}
