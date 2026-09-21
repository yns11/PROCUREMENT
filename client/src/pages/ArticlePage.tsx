import { Fragment, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Calculator, Download, Plus } from "lucide-react";
import { useCells, useProjection, useWrite } from "@/lib/queries";
import { usePerimeter } from "@/state/PerimeterContext";
import { api } from "@/lib/api";
import { Button, Card, Empty, ErrorBox, Kpi, Segmented, SeverityBadge, Skeleton, SkeletonBlock, Tabs, useToast } from "@/components/ui";
import { StockChart, CoverageChart } from "@/components/charts/StockChart";
import { EntryDrawer, type EntryDraft } from "@/components/EntryDrawer";
import { KIND_LABELS, ORDER_TYPE_LABELS, fmtDate, fmtQty, isWeekend, periodLabel } from "@/lib/format";
import type { CbnReport, CellKind, CellOut, ProjectionResponse } from "@/lib/types";

/** Rows of the grid whose cells are typed directly (quantity or arithmetic expression). */
const CELL_ROWS: Record<string, CellKind> = { supply_planned: "sim_order", adjustments: "adjustment" };

const PIVOT_ROWS: { key: string; label: string; group?: string; cls?: (v: number, a: ProjectionResponse["article"]) => string }[] = [
  { key: "demand", label: "Besoin (composants)", group: "Besoins" },
  { key: "demand_plan", label: "dont plan seul", group: "Besoins" },
  { key: "supply_firm", label: "Commandes fermes", group: "Approvisionnements" },
  { key: "supply_forecast", label: "Commandes prévisionnelles", group: "Approvisionnements" },
  { key: "supply_planned", label: "Commandes simulées", group: "Approvisionnements", cls: (v) => (v !== 0 ? "sim" : "") },
  { key: "receipts", label: "Réceptions", group: "Approvisionnements" },
  { key: "adjustments", label: "Ajustements", group: "Approvisionnements" },
  { key: "stock_firm", label: "Stock ferme", group: "Stocks", cls: () => "stock" },
  { key: "stock_forecast", label: "Stock prévisionnel", group: "Stocks", cls: () => "stock" },
  { key: "stock_sim", label: "Stock simulé", group: "Stocks", cls: () => "stock" },
  { key: "shortage_firm", label: "Manque ferme (besoin non servi)", group: "Manques", cls: (v) => (v > 0 ? "neg" : "") },
  { key: "shortage_forecast", label: "Manque prévisionnel", group: "Manques", cls: (v) => (v > 0 ? "neg" : "") },
  { key: "shortage_sim", label: "Manque simulé", group: "Manques", cls: (v) => (v > 0 ? "neg" : "") },
  { key: "coverage_firm", label: "Couverture ferme (j)", group: "Couverture", cls: (v, a) => (v <= a.alert_red_days ? "red" : v <= a.alert_yellow_days ? "yellow" : v >= a.overstock_days ? "green" : "") },
  { key: "coverage_forecast", label: "Couverture prévisionnelle (j)", group: "Couverture", cls: (v, a) => (v <= a.alert_red_days ? "red" : v <= a.alert_yellow_days ? "yellow" : v >= a.overstock_days ? "green" : "") },
  { key: "coverage_sim", label: "Couverture simulée (j)", group: "Couverture", cls: (v, a) => (v <= a.alert_red_days ? "red" : v <= a.alert_yellow_days ? "yellow" : v >= a.overstock_days ? "green" : "") },
];

export default function ArticlePage() {
  const { articleId } = useParams();
  const { perimeter, set, engineParams } = usePerimeter();
  const [tab, setTab] = useState<"table" | "events" | "cells" | "alerts" | "master">("table");
  const [draft, setDraft] = useState<EntryDraft | null>(null);
  const [editing, setEditing] = useState<{ key: string; i: number; value: string } | null>(null);
  const q = useProjection(articleId);
  const cells = useCells(articleId ? { article_id: articleId, scenario_id: engineParams.scenario_id } : undefined);
  const toast = useToast();
  const saveCell = useWrite((c: { date: string; kind: CellKind; expression: string }) => api.put<CellOut | null>("/api/entries/cells", { article_id: articleId, scenario_id: engineParams.scenario_id, ...c }),
    (out) => toast.push(out ? `${out.kind === "sim_order" ? "Commande simulée" : "Ajustement"} ${fmtDate(out.date)} = ${fmtQty(out.qty)}` : "Cellule effacée", "success"));
  const cbn = useWrite(() => api.post<CbnReport>("/api/cbn/run", { article_ids: [articleId], scenario_id: engineParams.scenario_id, params: { horizon_days: engineParams.horizon_days } }),
    (r) => toast.push(r.proposals ? `Calcul CBN : ${r.proposals} commande(s) simulée(s) ajoutée(s) (${fmtQty(r.qty)}), ${r.urgent} urgente(s)` : "Calcul CBN : aucun besoin net, rien à ajouter", r.urgent ? "info" : "success"));

  const d = q.data;
  const asOfIdx = useMemo(() => d ? d.period_start.findIndex((p, i) => p <= d.as_of && (d.period_start[i + 1] ?? "9999-12-31") > d.as_of) : -1, [d]);
  const series = useMemo(() => Object.fromEntries((d?.series ?? []).map((s) => [s.key, s.values])), [d]);
  const eventsByPeriod = useMemo(() => {
    const m = new Map<number, ProjectionResponse["events"]>();
    if (!d) return m;
    d.events.forEach((e) => {
      const i = d.period_start.findIndex((p, k) => p <= e.date && (d.period_start[k + 1] ?? "9999-12-31") > e.date);
      if (i >= 0) m.set(i, [...(m.get(i) ?? []), e]);
    });
    return m;
  }, [d]);
  /** cells of the grid grouped by (kind, period index) */
  const cellsByPeriod = useMemo(() => {
    const m = new Map<string, CellOut[]>();
    if (!d || !cells.data) return m;
    cells.data.forEach((c) => {
      const i = d.period_start.findIndex((p, k) => p <= c.date && (d.period_start[k + 1] ?? "9999-12-31") > c.date);
      if (i >= 0) m.set(`${c.kind}:${i}`, [...(m.get(`${c.kind}:${i}`) ?? []), c]);
    });
    return m;
  }, [d, cells.data]);

  const startEdit = (key: string, i: number, current: number) => {
    if (!d) return;
    if (perimeter.granularity !== "day") { set({ granularity: "day" }); toast.push("Passez au jour souhaité pour saisir une quantité", "info"); return; }
    const kind = CELL_ROWS[key];
    const own = cellsByPeriod.get(`${kind}:${i}`) ?? [];
    // one cell: edit its expression ; several (typed + CBN, or several days of a week): edit the total
    const value = own.length === 1 ? (own[0].expression || String(own[0].qty)) : current ? String(current) : "";
    setEditing({ key, i, value });
  };
  const commitEdit = (next?: { key: string; i: number }) => {
    if (!editing || !d) return;
    const kind = CELL_ROWS[editing.key];
    const own = cellsByPeriod.get(`${kind}:${editing.i}`) ?? [];
    const previous = own.length === 1 ? (own[0].expression || String(own[0].qty)) : "";
    if (editing.value.trim() !== previous.trim()) {
      const date = own.length >= 1 && own.every((c) => c.date === own[0].date) ? own[0].date : d.period_start[editing.i];
      saveCell.mutate({ date, kind, expression: editing.value });
    }
    setEditing(next ? { ...next, value: "" } : null);
    if (next) startEdit(next.key, next.i, 0);
  };

  if (!articleId) return <Empty title="Article non précisé" />;
  if (q.isError) return <ErrorBox error={q.error} retry={() => q.refetch()} />;
  const a = d?.article;
  const k = d?.kpis;
  const exportUrl = api.downloadUrl("/api/exports/simulation.xlsx", { article_ids: [articleId], scenario_id: engineParams.scenario_id, granularity: perimeter.granularity, horizon_days: engineParams.horizon_days });

  return (
    <div className="page">
      <div className="page-header">
        <div className="title">
          <div className="row"><Link to="/articles" className="btn ghost sm"><ArrowLeft />Fiches articles</Link>{a && <SeverityBadge severity={k?.severity ?? null} />}</div>
          <h1 style={{ marginTop: 6 }}>{articleId} {a && <span className="muted" style={{ fontWeight: 400 }}>· {a.designation}</span>}</h1>

        </div>

      </div>

      <div className="grid kpis">
        <Kpi label="Stock à date" value={k ? fmtQty(k.stock_as_of_sim, a?.unit) : "…"} unit={a?.unit} />
        <Kpi label="Couverture simulée" value={k?.coverage_sim_days ?? "…"} unit="j" />
        <Kpi label="Besoin 30 j" value={k ? fmtQty(k.demand_next_30d, a?.unit) : "…"} unit={a?.unit} />
        <Kpi label="Commandes simulées" value={k ? fmtQty(k.open_planned_qty, a?.unit) : "…"} unit={a?.unit} tone="brand" />
      </div>

      <Card title="Projection du stock">
        {q.isLoading || !d ? <Skeleton h={300} /> : <><StockChart data={d} /><div style={{ marginTop: 8 }}><CoverageChart data={d} /></div></>}
      </Card>

      <Tabs value={tab} onChange={setTab} tabs={[
        { id: "table", label: "Tableau de simulation" },
        { id: "events", label: "Commandes & mouvements" },
        { id: "cells", label: "Commandes simulées & ajustements saisis" },
        { id: "alerts", label: "Alertes" },
        { id: "master", label: "Données de base" },
      ]} />

      {tab === "table" && (        <div className="poc-toolbar" role="toolbar" aria-label="Simulation">
          <Segmented size="sm" value={perimeter.granularity} onChange={(g) => set({ granularity: g })} options={[{ id: "day", label: "Jour" }, { id: "week", label: "Semaine" }]} />
          <Button variant="primary" disabled={cbn.isPending} onClick={() => cbn.mutate(undefined)} title="Recalcule les besoins nets et les écrit dans la ligne Commandes simulées (les cellules saisies à la main sont conservées)"><Calculator />{cbn.isPending ? "Calcul…" : "Calcul CBN"}</Button>
          <Button onClick={() => setDraft({ kind: "order", article_id: articleId, supplier_id: d?.suppliers[0]?.supplier_id ?? null })}><Plus />Saisir</Button>
          <a className="btn" href={exportUrl}><Download />Excel</a>
        </div>)}

      {tab === "table" && (q.isLoading || !d ? <SkeletonBlock rows={10} /> : (
        <Card flush tight>
          <div className="pivot">
            <table>
              <thead>
                <tr>
                  <th>Variable</th>
                  {d.periods.map((p, i) => <th key={p} className={`${i === asOfIdx ? "today" : ""} ${d.granularity === "week" ? "wk" : ""}`} title={d.period_start[i]}>{periodLabel(p, d.granularity)}</th>)}
                </tr>
              </thead>
              <tbody>
                {PIVOT_ROWS.map((r, ri) => {
                  const vals = series[r.key] ?? [];
                  const head = ri === 0 || PIVOT_ROWS[ri - 1].group !== r.group;
                  const cellKind = CELL_ROWS[r.key];
                  const editable = !!cellKind || r.key === "supply_firm" || r.key === "receipts";
                  const isEvent = r.key === "supply_firm" || r.key === "supply_forecast";
                  return (
                    <Fragment key={r.key}>
                      {head && <tr className="group-head" key={`g-${r.group}`}><td>{r.group}</td>{d.periods.map((p) => <td key={p} />)}</tr>}
                      <tr key={r.key}>
                        <td>{r.label}</td>
                        {vals.map((v, i) => {
                          const past = i < asOfIdx;
                          const own = cellKind ? cellsByPeriod.get(`${cellKind}:${i}`) : undefined;
                          const isEditing = editing?.key === r.key && editing.i === i;
                          const cls = [past ? "past" : "", i === asOfIdx ? "today" : "", v === 0 ? "zero" : "", r.cls ? r.cls(v, d.article) : "",
                            editable && !past ? "editable" : "", isEditing ? "editing" : "", own?.some((c) => c.source === "CBN") ? "cbn" : "",
                            isEvent && eventsByPeriod.get(i)?.some((e) => e.kind === "order") ? "event" : "",
                            eventsByPeriod.get(i)?.some((e) => e.late && e.kind === "order") && r.key === "supply_firm" ? "late" : "",
                            d.granularity === "day" && isWeekend(d.period_start[i]) ? "past" : ""].filter(Boolean).join(" ");
                          const title = cellKind
                            ? (own?.map((c) => `${fmtDate(c.date)} : ${c.expression || c.qty} = ${fmtQty(c.qty, d.article.unit)} (${c.source})${c.note ? ` – ${c.note}` : ""}`).join("\n") || (past ? "" : "Cliquer pour saisir une quantité ou une formule (ex. 2*600-50)"))
                            : eventsByPeriod.get(i)?.map((e) => `${KIND_LABELS[e.kind] ?? e.kind} ${e.ref} : ${fmtQty(e.qty, d.article.unit)} (${ORDER_TYPE_LABELS[e.order_type] ?? e.order_type}, ${e.source})`).join("\n");
                          const onClick = !editable || past || isEditing ? undefined
                            : cellKind ? () => startEdit(r.key, i, v)
                            : () => setDraft({ kind: r.key === "receipts" ? "receipt" : "order", article_id: articleId, date: d.period_start[i], supplier_id: d.suppliers[0]?.supplier_id ?? null, order_type: "FIRM" });
                          return <td key={i} className={cls} title={title} onClick={onClick}>
                            {isEditing ? (
                              <input className="cell-input" autoFocus value={editing.value} aria-label={`${r.label} ${periodLabel(d.periods[i], d.granularity)}`}
                                onChange={(e) => setEditing({ ...editing, value: e.target.value })}
                                onBlur={() => commitEdit()}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") { e.preventDefault(); commitEdit(); }
                                  else if (e.key === "Escape") { e.preventDefault(); setEditing(null); }
                                  else if (e.key === "Tab") { e.preventDefault(); const ni = i + (e.shiftKey ? -1 : 1); if (ni >= asOfIdx && ni < vals.length) commitEdit({ key: r.key, i: ni }); else commitEdit(); }
                                }} />
                            ) : r.key.startsWith("coverage") ? v : v === 0 ? "·" : fmtQty(v, d.article.unit)}
                          </td>;
                        })}
                      </tr>
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

        </Card>
      ))}

      {tab !== "table" && <section className="poc-pending" role="tabpanel" aria-label={tab} />}

      <EntryDrawer draft={draft} onClose={() => setDraft(null)} articles={a ? [{ article_id: a.article_id, designation: a.designation, unit: a.unit }] : []} />
    </div>
  );
}
