import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "@/components/layout/AppShell";
const CockpitPage = lazy(() => import("@/pages/CockpitPage"));
const ArticlesPage = lazy(() => import("@/pages/ArticlesPage"));
const ArticlePage = lazy(() => import("@/pages/ArticlePage"));
const ProposalsPage = lazy(() => import("@/pages/ProposalsPage"));
const ScenariosPage = lazy(() => import("@/pages/ScenariosPage"));
const EntriesPage = lazy(() => import("@/pages/EntriesPage"));
const ImportsPage = lazy(() => import("@/pages/ImportsPage"));
const ReferencePage = lazy(() => import("@/pages/ReferencePage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));

export default function App() {
  return (
    <Suspense fallback={<div role="status" className="page">Chargement du portefeuille…</div>}><Routes>
      <Route element={<AppShell />}>
        <Route index element={<CockpitPage />} />
        <Route path="/articles" element={<ArticlesPage />} />
        <Route path="/articles/:articleId" element={<ArticlePage />} />
        <Route path="/propositions" element={<ProposalsPage />} />
        <Route path="/simulation" element={<ScenariosPage />} />
        <Route path="/saisies" element={<EntriesPage />} />
        <Route path="/imports" element={<ImportsPage />} />
        <Route path="/referentiel" element={<ReferencePage />} />
        <Route path="/parametres" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes></Suspense>
  );
}
