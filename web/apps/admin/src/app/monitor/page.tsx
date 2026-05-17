import { PageHeader } from "@/components/page-header";
import MonitorDashboard from "./_components/MonitorDashboard";

export default function MonitorPage() {
  return (
    <div>
      <PageHeader title="即時監控" description="即時查看語音對話串流與系統延遲指標" />
      <MonitorDashboard />
    </div>
  );
}
