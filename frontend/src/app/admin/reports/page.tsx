import type { Metadata } from "next";

import { AdminReportManager } from "@/components/admin-report-manager";

export const metadata: Metadata = {
  title: "Reports",
};

export default function AdminReportsPage() {
  return <AdminReportManager />;
}
