import { api } from "@/lib/api";
import { useOverrides, useParamEffective, useParamSchema, useWrite } from "@/lib/queries";
import { Button, Card, ErrorBox, SkeletonBlock, useToast } from "@/components/ui";

const LABELS: Record<string,string> = {
  spread_rounding:"Répartition du PDP", consumption_offset_days:"Décalage de consommation (j)",
  coverage_unit:"Unité de couverture", target_policy:"Stock cible", shortage_policy:"Gestion des manques",
  coverage_tie_rule:"Égalité stock / besoin", frozen_days:"Période gelée (j)", respect_lead_time:"Respect du délai fournisseur",
  delivery_shift:"Décalage au lundi", receipt_timing:"Disponibilité des arrivages", lead_calendar:"Calendrier du délai",
};
const OPTIONS: Record<string,string> = {none:"Sans arrondi",exact:"Total conservé",per_day:"Arrondi par jour",calendar:"Jours calendaires",working:"Jours ouvrés",coverage_days:"Couverture",safety_qty:"Sécurité fixe",max:"Maximum",sum:"Somme",backlog:"Report",lost:"Perte",covered:"Couvert",not_covered:"Non couvert",earlier:"Lundi précédent admissible",later:"Lundi suivant admissible",before_demand:"Avant consommation",after_demand:"Après consommation"};
export default function SettingsPage() {
  const schema = useParamSchema();const effective = useParamEffective();const overrides = useOverrides();const toast = useToast();
  const write = useWrite((b:{field:string;value:unknown})=>api.put("/api/params/overrides",{scope:"global",key1:"",key2:"",...b}),()=>toast.push("Enregistré","success"));
  const remove = useWrite((id:string)=>api.del(`/api/params/overrides/${id}`));
  const reset = useWrite(()=>api.post("/api/poc/reset"),()=>toast.push("Données réinitialisées","success"));
  return <div className="page">
    <div className="page-header"><h1>Paramètres</h1><Button disabled={reset.isPending} onClick={()=>{if(window.confirm("Réinitialiser toutes les données du POC ?"))reset.mutate(undefined);}}>Réinitialiser la démonstration</Button></div>
    {(schema.error || effective.error || write.error || reset.error) && <ErrorBox error={schema.error ?? effective.error ?? write.error ?? reset.error} />}
    <Card flush>{!schema.data || !effective.data ? <SkeletonBlock /> : <table className="tbl">
      <thead><tr><th>Paramètre</th><th>Valeur</th><th>Actions</th></tr></thead>
      <tbody>{schema.data.filter(p=>LABELS[p.field]).map(p=>{
        const cur=effective.data![p.field];const ov=overrides.data?.find(o=>o.scope==="global"&&o.field===p.field);
        return <tr key={p.field}><td>{LABELS[p.field]}</td><td>
          {p.options ? <select aria-label={LABELS[p.field]} className="select" value={String(cur)} onChange={e=>write.mutate({field:p.field,value:e.target.value})}>
            {p.options.map(o=><option key={o} value={o}>{OPTIONS[o]??o}</option>)}
          </select> : p.type==="bool" ? <input aria-label={LABELS[p.field]} type="checkbox" checked={Boolean(cur)} onChange={e=>write.mutate({field:p.field,value:e.target.checked})} /> :
            <input key={`${p.field}:${cur}`} aria-label={LABELS[p.field]} className="input" type="number" defaultValue={String(cur??"")} onBlur={e=>{if(e.target.value!==String(cur??""))write.mutate({field:p.field,value:Number(e.target.value)});}} />}
        </td><td>{ov&&<Button size="sm" onClick={()=>remove.mutate(ov.id)}>Rétablir</Button>}</td></tr>;
      })}<tr><td>Livraisons CBN</td><td>Lundi</td><td /></tr><tr><td>Commandes prévisionnelles</td><td>Lundi de la même semaine</td><td /></tr></tbody>
    </table>}</Card>
  </div>;
}
