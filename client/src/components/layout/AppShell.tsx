import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { usePerimeter } from "@/state/PerimeterContext";
import { Button, ErrorBox } from "@/components/ui";
import { fmtDate } from "@/lib/format";

const NAV = [
  { to: "/referentiel", label: "Référentiel" },
  { to: "/pdp", label: "PDP" },
  { to: "/commandes", label: "Commandes" },
  { to: "/articles", label: "Fiches articles" },
  { to: "/parametres", label: "Paramètres" },
];
export default function AppShell() {
  const { perimeter, set, config, configError } = usePerimeter();
  const [open, setOpen] = useState(false);
  return <div className="shell poc-shell">
    <a className="skip-link" href="#main-content">Aller au contenu</a>
    <aside className={`sidebar ${open ? "open" : ""}`}>
      <nav aria-label="Navigation" onClick={() => setOpen(false)}>
        {NAV.map(n => <NavLink key={n.to} to={n.to} className={({ isActive }) => isActive ? "active" : ""}>{n.label}</NavLink>)}
      </nav>
    </aside>
    <div className="main">
      <header className="topbar">
        <Button id="poc-menu" aria-expanded={open} onClick={() => setOpen(!open)}>Menu</Button>
        <div className="ctx"><label className="row">Horizon
          <select aria-label="Horizon" className="select sm" value={perimeter.horizonDays} onChange={e => set({ horizonDays: Number(e.target.value) })}>
            {[30,60,90,120].map(h => <option key={h} value={h}>{h} jours</option>)}
          </select></label>
        </div>
        <div className="right row"><span>Date de référence : <b>{config ? fmtDate(config.as_of) : "…"}</b></span>
          <select aria-label="Thème" className="select sm" value={perimeter.theme} onChange={e => set({ theme: e.target.value as typeof perimeter.theme })}>
            <option value="light">Clair</option><option value="dark">Sombre</option><option value="system">Système</option>
          </select>
        </div>
      </header>
      <main id="main-content" className="content" tabIndex={-1}>{configError ? <ErrorBox error={configError} /> : <Outlet />}</main>
    </div>
  </div>;
}
