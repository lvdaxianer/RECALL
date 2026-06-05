import { useState } from "react";

import { AppShell } from "../components/layout/AppShell";
import { ChatAssistant } from "../features/chat/ChatAssistant";
import { DocumentIngestPage } from "../features/documents/DocumentIngestPage";
import { EvaluationPage } from "../features/evaluation/EvaluationPage";
import { HomePage } from "../features/home/HomePage";
import { KnowledgeBaseListPage } from "../features/kb/KnowledgeBaseListPage";
import { RetrievalConsolePage } from "../features/retrieval/RetrievalConsolePage";
import { SettingsPage } from "../features/settings/SettingsPage";

export function App() {
  const [activeNav, setActiveNav] = useState("首页");

  return (
    <AppShell activeNav={activeNav} onNavigate={setActiveNav} title="Recall 知识库检索控制台">
      {activeNav === "首页" ? <HomePage /> : null}
      {activeNav === "知识库管理" ? <KnowledgeBaseListPage /> : null}
      {activeNav === "文档录入" ? <DocumentIngestPage /> : null}
      {activeNav === "检索调试" ? <RetrievalConsolePage /> : null}
      {activeNav === "效果评测" ? <EvaluationPage /> : null}
      {activeNav === "设置" ? <SettingsPage /> : null}
      <ChatAssistant />
    </AppShell>
  );
}
