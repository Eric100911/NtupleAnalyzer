import ROOT, math, time, json, argparse
from pathlib import Path
from collections import Counter
import pyarrow as pa, pyarrow.parquet as pq
ROOT.gROOT.SetBatch(True)
parser = argparse.ArgumentParser()
parser.add_argument('--inventory-dir', type=Path, required=True)
parser.add_argument('--mc-dir', type=Path, required=True)
args = parser.parse_args()
out = args.inventory_dir
out.mkdir(parents=True, exist_ok=True)
mcdir = args.mc_dir

def rapidity(pt,eta,mass):
 mt=math.hypot(pt,mass); pz=pt*math.sinh(eta); energy=math.hypot(mt,pz)
 if energy<=abs(pz):return float('nan')
 return 0.5*math.log((energy+pz)/(energy-pz))
def flavor(pdg):
 a=abs(int(pdg))
 if a==553 or a<100 or a>=1_000_000_000:return None
 ds={(a//1000)%10,(a//100)%10,(a//10)%10}
 if 5 in ds:return 'beauty'
 if 4 in ds:return 'charm'
 return None
def ancestry(pdg,mints,mids,idx):
 if idx is None:return 'ambiguous_ancestry',[],False
 chain=[];cur=int(idx);seen=set();charm=False
 for _ in range(50):
  if cur in seen or not 0<=cur<len(pdg):return ('charm_ancestor_beauty_upstream_unresolved' if charm else 'ambiguous_ancestry'),chain,False
  seen.add(cur); im=int(mints[cur]); mi=int(mids[cur])
  chain.append({'idx':cur,'pdg':int(pdg[cur]),'mother_pdg_evidence':im,'mother_idx':mi})
  f=flavor(im)
  if f=='beauty':return 'beauty_ancestor',chain,False
  if f=='charm':charm=True
  if mi<0 or mi>=len(pdg):
   return ('charm_ancestor_beauty_upstream_unresolved' if charm else 'ambiguous_ancestry'),chain,False
  if int(pdg[mi])!=im:
   return ('charm_ancestor_beauty_upstream_unresolved' if charm else 'ambiguous_ancestry'),chain,False
  cur=mi
 return ('charm_ancestor_beauty_upstream_unresolved' if charm else 'ambiguous_ancestry'),chain,False

def convert(v):
 if isinstance(v,float) and not math.isfinite(v):return None
 return v
files=sorted(mcdir.glob('*.root'))
required=['MC_GenPart_pdgId','MC_GenPart_status','MC_GenPart_motherPdgId','MC_GenPart_motherGenIdx','MC_GenPart_pt','MC_GenPart_eta','MC_GenPart_mass','bestCandIdx','Phi_K_1_genMatchIdx','Phi_K_2_genMatchIdx','Phi_K_1_genMatchSource','Phi_K_2_genMatchSource','sel_Phi_mass','sel_Phi_ctau','sel_Phi_ctauErr','sel_Phi_pt','sel_Phi_eta','sel_Phi_px','sel_Phi_py','sel_Phi_pz','sel_Phi_VtxProb','sel_Phi_Chi2','sel_Phi_ndof','sel_Pri_ctau','sel_Pri_ctauErr','sel_Pri_VtxProb','sel_Pri_Chi2','sel_Pri_ndof','sel_Jpsi_1_mass','sel_Jpsi_2_mass','runNum','lumiNum','evtNum']
all_reports=[]
for path in files:
 start=time.time(); f=ROOT.TFile.Open(str(path),'READ'); t=f.Get('selected'); total=int(t.GetEntries());t.SetBranchStatus('*',0)
 missing=[]
 for name in required:
  if t.GetBranch(name):t.SetBranchStatus(name,1)
  else:missing.append(name)
 if missing:raise RuntimeError(f'{path}: missing required branches {missing}')
 if t.GetBranch('genWeight'):t.SetBranchStatus('genWeight',1)
 names=['sample','run','lumi','event','source_file','entry','bestCandIdx','phi_ctau_cm','phi_ctauErr_cm','phi_pt','phi_y','phi_mass','phi_VtxProb','phi_Chi2','phi_ndof','Pri_ctau_cm','Pri_ctauErr_cm','Pri_VtxProb','Pri_Chi2','Pri_ndof','jpsi1_mass','jpsi2_mass','matched_phi_gen_idx','workflow_phi_gen_idx','workflow_target_match','match_contract_verified','origin_category','origin_chain','origin_chain_complete','genWeight']
 schema=pa.schema([('sample',pa.string()),('run',pa.int64()),('lumi',pa.int64()),('event',pa.int64()),('source_file',pa.string()),('entry',pa.int64()),('bestCandIdx',pa.int64()),('phi_ctau_cm',pa.float64()),('phi_ctauErr_cm',pa.float64()),('phi_pt',pa.float64()),('phi_y',pa.float64()),('phi_mass',pa.float64()),('phi_VtxProb',pa.float64()),('phi_Chi2',pa.float64()),('phi_ndof',pa.float64()),('Pri_ctau_cm',pa.float64()),('Pri_ctauErr_cm',pa.float64()),('Pri_VtxProb',pa.float64()),('Pri_Chi2',pa.float64()),('Pri_ndof',pa.float64()),('jpsi1_mass',pa.float64()),('jpsi2_mass',pa.float64()),('matched_phi_gen_idx',pa.int64()),('workflow_phi_gen_idx',pa.int64()),('workflow_target_match',pa.bool_()),('match_contract_verified',pa.bool_()),('origin_category',pa.string()),('origin_chain',pa.string()),('origin_chain_complete',pa.bool_()),('genWeight',pa.float64())])
 allpath=out/(path.stem+'_full_selected.parquet'); recodpath=out/(path.stem+'_RECOD_target_matched.parquet')
 wa=pq.ParquetWriter(allpath,schema,compression=None); wr=pq.ParquetWriter(recodpath,schema,compression=None)
 counts=Counter(); keys=Counter(); batch=[]; recbatch=[]; examples=[]; tstart=time.time()
 for ent in range(total):
  t.GetEntry(ent);counts['entries']+=1
  pdg=list(t.MC_GenPart_pdgId); mints=list(t.MC_GenPart_motherPdgId); mids=list(t.MC_GenPart_motherGenIdx); gpt=list(t.MC_GenPart_pt); geta=list(t.MC_GenPart_eta); gm=list(t.MC_GenPart_mass)
  for j,m in enumerate(mids):
   if m<0 and mints[j]!=0:counts['mother_index_skipped_immediate_mother_nonzero_nodes']+=1
   elif 0<=m<len(pdg) and pdg[m]!=mints[j]:counts['mother_index_pdg_inconsistencies']+=1
  kids={}
  for j,m in enumerate(mids):
   if 0<=m<len(pdg):kids.setdefault(m,[]).append(j)
  eligible_jpsi=[]
  for j,pdgid in enumerate(pdg):
   if abs(pdgid)==443 and gpt[j]>6 and abs(rapidity(gpt[j],geta[j],gm[j]))<2.5:eligible_jpsi.append(j)
  eligible_phi=[]
  for j,pdgid in enumerate(pdg):
   if abs(pdgid)==333:
    nk=sum(abs(pdg[x])==321 for x in kids.get(j,[]))
    if nk>=2 and gpt[j]>4 and abs(rapidity(gpt[j],geta[j],gm[j]))<2.4:eligible_phi.append(j)
  target=max(eligible_phi,key=lambda j:gpt[j]) if eligible_phi and len(eligible_jpsi)>=2 else None
  best=int(t.bestCandIdx);a=list(t.Phi_K_1_genMatchIdx);b=list(t.Phi_K_2_genMatchIdx);s1=list(t.Phi_K_1_genMatchSource);s2=list(t.Phi_K_2_genMatchSource)
  k1=a[best] if 0<=best<len(a) else -1;k2=b[best] if 0<=best<len(b) else -1
  src1=s1[best] if 0<=best<len(s1) else -1;src2=s2[best] if 0<=best<len(s2) else -1
  p1=mids[k1] if 0<=k1<len(mids) else -1;p2=mids[k2] if 0<=k2<len(mids) else -1
  selected=p1 if p1==p2 and 0<=p1<len(pdg) and abs(pdg[p1])==333 else None
  match=selected is not None and src1==1 and src2==1
  targetmatch=selected is not None and target is not None and selected==target
  if match:counts['final_best_source1_common_phi']+=1
  if target is not None:counts['workflow_proxy_target_exists']+=1
  else:counts['no_workflow_proxy_target']+=1
  if targetmatch:counts['workflow_target_match']+=1
  elif selected is not None and target is not None:counts['workflow_target_mismatch']+=1
  else:counts['no_comparable_target_match']+=1
  origin,chain,complete=ancestry(pdg,mints,mids,selected)
  counts['origin_'+origin]+=1
  if complete:counts['ancestry_complete']+=1
  if selected is not None: counts['matched_phi_parent_found']+=1
  else:counts['no_matched_phi_parent']+=1
  ptx=float(t.sel_Phi_px);pty=float(t.sel_Phi_py);ptz=float(t.sel_Phi_pz);mass=float(t.sel_Phi_mass);pt=math.hypot(ptx,pty);energy=math.sqrt(pt*pt+ptz*ptz+mass*mass)
  y=0.5*math.log((energy+ptz)/(energy-ptz)) if energy>abs(ptz) else float('nan')
  rec={'sample':path.stem,'run':int(t.runNum),'lumi':int(t.lumiNum),'event':int(t.evtNum),'source_file':str(path),'entry':ent,'bestCandIdx':best,'phi_ctau_cm':float(t.sel_Phi_ctau),'phi_ctauErr_cm':float(t.sel_Phi_ctauErr),'phi_pt':float(t.sel_Phi_pt),'phi_y':y,'phi_mass':mass,'phi_VtxProb':float(t.sel_Phi_VtxProb),'phi_Chi2':float(t.sel_Phi_Chi2),'phi_ndof':float(t.sel_Phi_ndof),'Pri_ctau_cm':float(t.sel_Pri_ctau),'Pri_ctauErr_cm':float(t.sel_Pri_ctauErr),'Pri_VtxProb':float(t.sel_Pri_VtxProb),'Pri_Chi2':float(t.sel_Pri_Chi2),'Pri_ndof':float(t.sel_Pri_ndof),'jpsi1_mass':float(t.sel_Jpsi_1_mass),'jpsi2_mass':float(t.sel_Jpsi_2_mass),'matched_phi_gen_idx':selected,'workflow_phi_gen_idx':target,'workflow_target_match':bool(targetmatch),'match_contract_verified':bool(match),'origin_category':origin,'origin_chain':json.dumps(chain,separators=(',',':')),'origin_chain_complete':complete,'genWeight':float(t.genWeight) if t.GetBranch('genWeight') else None}
  keys[(rec['run'],rec['lumi'],rec['event'])]+=1; batch.append(rec)
  if match and targetmatch:recbatch.append(rec)
  if len(examples)<10 and (not match or not targetmatch or origin=='beauty_ancestor'):examples.append({'entry':ent,'event_key':[rec['run'],rec['lumi'],rec['event']],'source1_match':match,'selected_phi_gen_idx':selected,'workflow_phi_gen_idx':target,'workflow_target_match':targetmatch,'origin_category':origin,'origin_chain':chain})
  if len(batch)>=2000:wa.write_table(pa.Table.from_pylist(batch,schema=schema));batch=[]
  if len(recbatch)>=2000:wr.write_table(pa.Table.from_pylist(recbatch,schema=schema));recbatch=[]
 if batch:wa.write_table(pa.Table.from_pylist(batch,schema=schema))
 if recbatch:wr.write_table(pa.Table.from_pylist(recbatch,schema=schema))
 wa.close();wr.close();f.Close()
 dup={str(k):v for k,v in keys.items() if v>1}
 report={'sample':path.stem,'path':str(path),'tree':'selected','entries':total,'full_selected_parquet':allpath.name,'recod_target_matched_parquet':recodpath.name,'recod_rows':counts['workflow_target_match'],'event_key_unique':len(keys),'event_key_duplicate_groups':len(dup),'event_key_duplicate_rows':sum(v-1 for v in dup.values()),'duplicate_examples':dict(list(dup.items())[:20]),'counts':dict(counts),'missing_required_branches':missing,'elapsed_seconds':time.time()-start,'pilot_elapsed_seconds_previous':'~0.2-0.5 s per 200 rows','sample_examples':examples,'genWeight_branch_present':bool(counts['entries'] and t.GetBranch('genWeight')) if False else None}
 report['genWeight_branch_present']='genWeight' in required
 (out/(path.stem+'_full_extraction_summary.json')).write_text(json.dumps(report,indent=2)+'\n')
 all_reports.append(report);print(path.stem,'done',total,'rows',counts['workflow_target_match'],'RECO-D rows',report['elapsed_seconds'],'s',flush=True)
(out/'full_selected_mc_extraction_summary.json').write_text(json.dumps({'scope':'full local selected MC files only; row preserving; RECO-D subset requires source=1 common direct phi parent plus highest-pT workflow-target match','samples':all_reports},indent=2)+'\n')
