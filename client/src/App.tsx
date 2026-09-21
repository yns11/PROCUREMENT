import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "@/components/layout/AppShell";
const ArticlesPage = lazy(() => import("@/pages/ArticlesPage"));
const ArticlePage = lazy(() => import("@/pages/ArticlePage"));
const PocDataPage = lazy(() => import("@/pages/PocDataPage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));

export default function App() {
  return <Suspense fallback={<div role="status" className="page">Chargement…</div>}><Routes>
    <Route element={<AppShell />}>
      <Route index element={<Navigate to="/articles" replace />} />
      <Route path="/articles" element={<ArticlesPage />} />
      <Route path="/articles/:articleId" element={<ArticlePage />} />
      <Route path="/referentiel" element={<PocDataPage section="reference" />} />
      <Route path="/pdp" element={<PocDataPage section="pdp" />} />
      <Route path="/commandes" element={<PocDataPage section="orders" />} />
      <Route path="/parametres" element={<SettingsPage />} />
      <Route path="*" element={<Navigate to="/articles" replace />} />
    </Route>
  </Routes></Suspense>;
}
