import Workbench from "../../../components/Workbench";
export default async function DiagnosisPage({ params }: { params: Promise<{ diagnosisRunId: string }> }) {
  const { diagnosisRunId } = await params;
  return <Workbench initialRunId={diagnosisRunId} />;
}
