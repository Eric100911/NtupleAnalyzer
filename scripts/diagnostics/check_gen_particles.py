from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

"""Check whether MC_GenPart_* arrays have content in a TPS-Onia2MuMu ntuple."""
import sys
import awkward as ak
import uproot

PATH = sys.argv[1] if len(sys.argv) > 1 else (
    "root://cceos.ihep.ac.cn//store/user/chiw/MC_Production_v3/"
    "JpsiJpsiPhi/Ntuple/DPS-JpsiJpsi-Phi-LO/"
    "DPS-JpsiJpsi-Phi-LO-Ntuple-v01_06-168.root"
)

with uproot.open(f"{PATH}:mkcands/X_data") as f:
    n_total = f.num_entries
    arrs = f.arrays(["MC_GenPart_pdgId"], library="ak", entry_stop=min(n_total, 100))

n_gen_parts = ak.sum(ak.num(arrs["MC_GenPart_pdgId"], axis=1) > 0)
n_events = len(arrs["MC_GenPart_pdgId"])
print(f"File: {PATH}")
print(f"Total entries: {n_total}, checked first {n_events}")
print(f"Events with >0 GEN particles: {n_gen_parts}/{n_events}")

if n_gen_parts > 0:
    pdg = arrs["MC_GenPart_pdgId"]
    n_jpsi = ak.sum(ak.any(abs(pdg) == 443, axis=1))
    n_phi = ak.sum(ak.any(abs(pdg) == 333, axis=1))
    print(f"Events with GEN J/psi: {n_jpsi}, GEN phi: {n_phi}")
