import type { Metadata } from "next";

import { AdminWordManager } from "@/components/admin-word-manager";

export const metadata: Metadata = {
  title: "Words",
};

export default function AdminWordsPage() {
  return <AdminWordManager />;
}
