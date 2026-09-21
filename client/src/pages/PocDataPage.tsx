import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useWrite } from "@/lib/queries";
import { Button, Card, ErrorBox, SkeletonBlock, Tabs, useToast } from "@/components/ui";

type Row = Record<string, string | number>;
type TableName = "articles" | "bom" | "pdp" | "orders";
interface Column { key: string; label: string; type: string; choices?: string[]; default: string | number }
interface TableData { rows: Row[]; columns: Column[]; keys: string[] }

export default function PocDataPage({section}: {section: "reference" | "pdp" | "orders"}) {
  const [tab, setTab] = useState<"articles" | "bom">("articles");
  const table = section === "reference" ? tab : section;
  return <div className="page">
    <div className="page-header"><h1>{section === "reference" ? "Référentiel" : section === "pdp" ? "PDP" : "Commandes"}</h1></div>
    {section === "reference" && <Tabs value={tab} onChange={setTab} tabs={[{id:"articles",label:"Articles"},{id:"bom",label:"Nomenclatures (BOM)"}]} />}
    <TableEditor key={table} table={table} />
  </div>;
}

function TableEditor({table}: {table: TableName}) {
  const query = useQuery({queryKey:["poc-table",table], queryFn:()=>api.get<TableData>(`/api/poc/tables/${table}`)});
  const [draft, setDraft] = useState<Row[] | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const toast = useToast();
  const rows = draft ?? query.data?.rows ?? [];
  const dirty = draft !== null;
  const save = useWrite((newRows: Row[])=>api.put<{rows:Row[]}>(`/api/poc/tables/${table}`,{rows:newRows}), ()=>{
    setDraft(null);setError(null);toast.push("Enregistré", "success");
  });
  useEffect(()=>{
    const unload = (e: BeforeUnloadEvent) => { if (dirty) {e.preventDefault();} };
    // Include in-app navigation: canceling keeps the draft on screen.
    const navigate = (e: MouseEvent) => {
      const target = e.target instanceof Element ? e.target.closest("a[href], button[role=tab]") : null;
      if (dirty && target && !target.hasAttribute("download") && !window.confirm("Abandonner les modifications ?")) {
        e.preventDefault();e.stopPropagation();
      }
    };
    window.addEventListener("beforeunload",unload);document.addEventListener("click",navigate,true);
    return ()=>{window.removeEventListener("beforeunload",unload);document.removeEventListener("click",navigate,true);};
  },[dirty]);
  const upload = async (f?: File) => {
    if(!f)return;
    setLoading(true);setError(null);
    try { const form = new FormData();form.append("file",f);
      const result = await api.upload<{rows:Row[]}>(`/api/poc/parse/${table}`,form);
      setDraft(result.rows);
    } catch(e){setError(e as Error);} finally {setLoading(false);if(file.current)file.current.value="";}
  };
  const edit = (i:number,key:string,value:string|number) => setDraft(rows.map((r,j)=>j===i?{...r,[key]:value}:r));
  if(query.isError)return <ErrorBox error={query.error} retry={()=>query.refetch()} />;
  if(!query.data)return <SkeletonBlock />;
  return <>
    <div className="poc-toolbar" role="toolbar" aria-label="Édition des données">
      <Button onClick={()=>file.current?.click()} disabled={loading}>{loading?"Chargement…":"Charger"}</Button>
      <input ref={file} aria-label="Fichier à charger" type="file" accept=".csv,.xlsx" hidden onChange={e=>upload(e.target.files?.[0])} />
      <a className="btn" download href={api.downloadUrl(`/api/poc/templates/${table}.csv`)}>Exemple CSV</a>
      <Button onClick={()=>setDraft([...rows,Object.fromEntries(query.data!.columns.map(c=>[c.key,c.default]))])}>Ajouter une ligne</Button>
      <Button variant="primary" disabled={!dirty || save.isPending} onClick={()=>save.mutate(rows)}>Enregistrer</Button>
      <Button disabled={!dirty || save.isPending} onClick={()=>{setDraft(null);setError(null);}}>Annuler</Button>
      <span className="badge neutral">{rows.length} lignes</span>{dirty && <span className="badge warning">Non enregistré</span>}
    </div>
    {(error || save.error) && <ErrorBox error={error ?? save.error} />}
    <Card flush><div className="table-wrap poc-editor"><table className="tbl compact">
      <thead><tr>{query.data.columns.map(c=><th key={c.key}>{c.label}</th>)}<th>Actions</th></tr></thead>
      <tbody>{rows.map((row,i)=><tr key={i}>{query.data!.columns.map(c=><td key={c.key}>
        {c.choices ? <select className="select sm" aria-label={`${c.label} ligne ${i+1}`} value={row[c.key]??""} onChange={e=>edit(i,c.key,e.target.value)}>
          <option value="">—</option>{c.choices.map(x=><option key={x} value={x}>{x==="FIRM"?"Ferme":x==="FORECAST"?"Prévisionnelle":x}</option>)}
        </select> : <input className="input sm" aria-label={`${c.label} ligne ${i+1}`} type={c.type==="date"?"date":["integer","number"].includes(c.type)?"number":"text"}
          step={c.type==="integer"?"1":"any"} value={row[c.key]??""} onChange={e=>edit(i,c.key,e.target.value===""?"":c.type==="number"||c.type==="integer"?Number(e.target.value):e.target.value)} />}
      </td>)}<td><Button size="sm" aria-label={`Supprimer ligne ${i+1}`} onClick={()=>setDraft(rows.filter((_,j)=>j!==i))}>Supprimer</Button></td></tr>)}</tbody>
    </table></div></Card>
  </>;
}
