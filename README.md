# NtupleAnalyzer assocPV Workflow

这个包现在按 assocPV merge/fit/plot 和 JJP efficiency 工作流运行。公开 channel 名称固定为：

- `JJP`: `J/psi + J/psi + phi`
- `JYP`: `J/psi + Upsilon + phi`
- `JJY`: `J/psi + J/psi + Upsilon`

`JUP` 和 `JJU` 不作为 CLI channel 名称使用；外部 EOS/XRootD 目录里已有的 `JUP_*` 或 `JpsiUpsPhi` 字符串只是存储命名。

主分析分 4 条工作流：

1. `merge_apply_cuts.py`
   合并全部 ntuple，做 assocPV 动力学 cut，事件内选最佳候选，输出带原始 branch 和统一 `sel_*` 标量分支的 ROOT 文件。
2. `fit_splot.py`
   对 cut 后样本做质量拟合和 `sPlot`，输出拟合图，并把 `signal_sw` 与各个 yield 的 sWeight 回写到 ROOT 文件。
3. `plot_weighted_distributions.py`
   用 `signal_sw` 为权重绘制所有 `sel_*` 物理量分布，并合并原有关联图功能。
4. Efficiency pipeline (`run_efficiency.py` → `merge_efficiency_shards.py` → `build_derived_efficiency.py`)
   从 GEN 级 ntuple 直接计算 J/ψ+J/ψ+φ 的 acceptance 和逐步 conditional efficiency，输出 binned maps 和 CMS-style plots。

所有默认输出都写到：

`/eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV`

推荐运行环境：

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh
```

## 输入路径

- DATA:
  - JJP: `/eos/user/c/chiw/JpsiJpsiPhi/rootNtuple`
  - JYP: `/eos/user/c/chiw/JpsiUpsPhi/rootNtuple`
  - JJY: `/eos/user/c/chiw/JpsiJpsiUps/rootNtuple`
- MC:
  - 基础目录: `/eos/ihep/cms/store/user/xcheng/MC_Production_v3/output`
  - 程序会自动转成 `root://cceos.ihep.ac.cn//eos/ihep/...` 并优先读取 `output_ntuple.root`
  - JJP 样本: `DPS_1`, `DPS_2_CS`, `DPS_2_G`, `SPS_CS`, `SPS_G`, `TPS`
  - JYP 样本: `SPS`, `DPS_1`, `DPS_2`, `DPS_3`, `TPS`
  - JJY 基础目录: `/eos/user/c/chiw/JpsiJpsiUps/MC_samples/rootNtuple_refactor`
  - JJY 样本: `DPS_1 = DPS-Jpsi-JpsiY/filter_JpsiPtMin4p0_YPtMin6p0`, `DPS_2 = DPS-JpsiJpsi-Y/filter_JpsiPtMin4p0_YPtMin6p0`
  - 默认 proxy: `/afs/cern.ch/user/c/chiw/condor/x509up`

## 选择标准

- JJP:
  - 所有 muon 默认要求 `soft`
  - muon: `abs(eta) < 1.2 => pT > 3.5`, `1.2 < abs(eta) < 2.4 => pT > 2.5`
  - `Jpsi mass in [2.9, 3.3]`
  - `Jpsi pT > 6`
  - `abs(y_Jpsi) < 2.5`
  - `Kaon pT > 2`
  - `abs(eta_K) < 2.5`
  - `Phi mass in [0.99, 1.07]`
  - `Phi pT > 4`
- JYP:
  - 继承上面的 J/psi、muon、Kaon、Phi cut
  - `Ups mass in [8.5, 11.4]`
  - `abs(y_Ups) < 2.5`
- JJY:
  - 两个 J/psi 默认要求 `soft` muon，Upsilon 默认要求 `soft` muon；可用 `--jpsi-muon-id` 和 `--ups-muon-id` 覆盖
  - `Jpsi_1/Jpsi_2 mass in [2.9, 3.3]`
  - `Ups mass in [8.5, 11.4]`
  - `Jpsi_1/Jpsi_2 pT > 3`, `Ups pT > 4`
  - `abs(y_Jpsi_1)`, `abs(y_Jpsi_2)`, `abs(y_Ups) < 2.5`
  - 6 个候选 muon index 必须有效且互不重复
  - JJY MC merge 默认不加 gen-match cut

多候选事件默认取 `sqrt(pt1^2 + pt2^2 + pt3^2)` 最大的候选。

## 核心脚本

- [ntuple_pipeline_common.py](ntuple_pipeline_common.py) — shared channel config, input discovery, C++ RDataFrame helpers
- [merge_apply_cuts.py](merge_apply_cuts.py) — merge + assocPV cuts + best-candidate selection
- [fit_splot.py](fit_splot.py) — mass fit + sPlot sWeights
- [plot_weighted_distributions.py](plot_weighted_distributions.py) — sWeight-weighted kinematic plots
- [run_efficiency.py](run_efficiency.py) → [efficiency_workflow/](efficiency_workflow/) — JJP efficiency pipeline
- [merge_efficiency_shards.py](merge_efficiency_shards.py) — merge sharded efficiency output
- [build_derived_efficiency.py](build_derived_efficiency.py) — derived acceptance/conditional/per-object/stacked maps and plots

## 本地运行

JJP data 全流程：

```bash
./run_jjp_analysis.sh
```

JYP data 全流程：

```bash
./run_jyp_analysis.sh
```

只跑 merge：

```bash
./run_assoc_merge.sh --channel JJP --dataset data
./run_assoc_merge.sh --channel JYP --dataset mc --sample DPS_3
./run_assoc_merge.sh --channel JJY --dataset mc --sample DPS_1 -j 1
./run_assoc_merge.sh --channel JJY --dataset mc --sample DPS_2 -j 1
./run_assoc_merge.sh --channel JJY --dataset data -j 1
```

只跑拟合：

```bash
./run_assoc_fit.sh --channel JJP --dataset data
./run_assoc_fit.sh --channel JJY --dataset mc --sample DPS_1 -j 1
```

只跑加权画图：

```bash
./run_assoc_plots.sh --channel JYP --dataset data
./run_assoc_plots.sh --channel JJY --dataset mc --sample DPS_1
```

## HTCondor

HTCondor 用于第 1 步 merge 和第 4 步 efficiency。

**Merge:**
- MC merge: `condor/jjp_mc.sub`, `condor/jyp_mc.sub`, `condor/jjy_mc.sub`
- DATA merge: `condor/jjp_data.sub`, `condor/jyp_data.sub`

**Efficiency:**
- `condor/jjp_efficiency.sub` — sharded efficiency jobs using runtime tarball

提交辅助脚本：

```bash
cd condor
./submit.sh jyp_mc --mode DPS_3
./submit.sh jjy_mc --mode all --jobs 1
./submit.sh jjp_data
./submit.sh jjp_efficiency
```

## JJP efficiency

The efficiency pipeline computes fiducial acceptance and per-step conditional efficiencies for J/ψ+J/ψ+φ events, binned in meson pT and rapidity. It works directly on GEN-level ntuples (not merged selected ROOT files). The first supported mode is `JpsiJpsiPhi`.

### Pipeline stages

1. **`run_efficiency.py`** — per-file efficiency shard: finds gen J/ψ+J/ψ+φ systems, matches reco candidates, computes cumulative step flags. Supports `--efficiency-backend vectorized|python-loop`, `--max-files N` for testing.
2. **`merge_efficiency_shards.py`** — merges shard outputs into per-sample files.
3. **`build_derived_efficiency.py`** — produces derived maps and plots from merged output.

### Quick test

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh

# One-file efficiency test
python3 run_efficiency.py --analysis-mode JpsiJpsiPhi \
  --output-dir /tmp/chiw/eff_test --max-files 1 --samples JJP_DPS2_CS --skip-plots

# Build derived products
python3 build_derived_efficiency.py --input-dir /tmp/chiw/eff_test
```

### Full run

```bash
./run_assoc_efficiency.sh \
  --samples JJP_DPS1,JJP_DPS2_CS,JJP_DPS2_G,JJP_SPS_CS,JJP_SPS_G \
  --output-dir /tmp/chiw/jjp_efficiency_v1
```

### Rebuild merged maps

Use `rebuild_efficiency_maps.py` when the merged `gen_systems.parquet` and
`event_step_flags.parquet` files are already available, but the binned map
schema or step definitions changed. The script is non-overwriting by default:
`--output-dir` must be a fresh tree, and the source parquet files are copied
next to the rebuilt maps for traceability.

```bash
python3 rebuild_efficiency_maps.py \
  --input-dir /eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/efficiency_HLTv2/merged \
  --output-dir /eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/efficiency_HLTv2/merged_yieldcorr_20260601 \
  --samples JJP_DPS1 JJP_DPS2_CS JJP_DPS2_G JJP_SPS_CS JJP_SPS_G

python3 build_derived_efficiency.py \
  --input-dir /eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/efficiency_HLTv2/merged_yieldcorr_20260601

python3 -m efficiency_workflow.build_factorized_maps \
  --input-dir /eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/efficiency_HLTv2/merged_yieldcorr_20260601 \
  --samples JJP_DPS1 JJP_DPS2_CS JJP_DPS2_G JJP_SPS_CS JJP_SPS_G
```

### Efficiency-corrected yield

The JJP corrected-yield workflow fits the selected data once without weights,
then builds one weighted mini-tree per MC subprocess correction and refits each tree.
The nominal central value currently uses `JJP_DPS1`; the systematic is the
subprocess envelope across the configured samples. The default correction is now
factorized:

```text
A(J/psi_1) * A(J/psi_2) * A(phi)
* eps_muReco(J/psi_1) * eps_muReco(J/psi_2)
* eps_muID(J/psi_1) * eps_muID(J/psi_2)
* eps_dimuon(J/psi_1) * eps_dimuon(J/psi_2)
* eps_kaonReco(phi) * eps_kaonID(phi) * eps_dikaon(phi)
* eps_HLT * eps_4mu_vtx * eps_triOnia
```

Each sample must have factorized maps under `<sample>/maps/`, produced by
`python3 -m efficiency_workflow.build_factorized_maps`. Lookup uses fine bins
first, then coarse bins, then inclusive bins. The defaults are
`--n-min-fine 30` and `--n-min-coarse 50`.

```bash
python3 compute_efficiency_corrected_yield.py \
  --data-input /eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/merged/jjp_data_selected.root \
  --efficiency-dir /eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/efficiency_HLTv2/merged_yieldcorr_20260601 \
  --output /tmp/chiw/jjp_efficiency_corrected_yield.json \
  --corrected-root /tmp/chiw/jjp_data_effcorr_selected.root \
  --plot-dir /tmp/chiw/jjp_efficiency_corrected_yield_plots \
  -j 4

python3 fit_splot.py \
  --channel JJP \
  --dataset data \
  -i /tmp/chiw/jjp_data_effcorr_selected.root \
  -o /tmp/chiw/jjp_data_effcorr_splot.root \
  --effcorr-weight-branch effcorr_weight \
  --plot-dir /tmp/chiw/jjp_effcorr_splot_fit_plots \
  -j 4

python3 plot_weighted_distributions.py \
  --channel JJP \
  --dataset data \
  -i /tmp/chiw/jjp_data_effcorr_splot.root \
  -o /tmp/chiw/jjp_effcorr_splot_dynamics \
  -w signal_effcorr_sw
```

The command prints status before each expensive stage: raw fit, map loading,
weighted-tree building, and per-sample weighted fits. The JSON contains the raw
yield, per-sample corrected yields, fallback counts, MC-stat uncertainty,
subprocess envelope, and total uncertainty. The optional `--corrected-root`
output preserves the full selected-tree schema and appends `effcorr_*` branches
for the sPlot dynamics chain. `fit_splot.py --effcorr-weight-branch` leaves the
mass fit unweighted and writes `signal_effcorr_sw = signal_sw * effcorr_weight`
for plotting.

For comparison with the previous single-map correction, run:

```bash
python3 compute_efficiency_corrected_yield.py \
  --correction-mode legacy-correlated \
  --data-input /eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/merged/jjp_data_selected.root \
  --efficiency-dir /eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/efficiency_HLTv2/merged_yieldcorr_20260601 \
  --efficiency-step Pri_assocPVPass \
  --map-type correlated_3d \
  --denominator absolute \
  -o /tmp/chiw/jjp_legacy_correlated_yield.json
```

### Move to a faster machine

For a faster interactive machine, move the code and parquet products separately.
Keep ROOT data files only if the target machine will run the mass fits.

```bash
# Code package, preserving committed history.
cd /afs/cern.ch/user/c/chiw/condor/NtupleAnalyzer
git bundle create /tmp/NtupleAnalyzer_efficiency.bundle HEAD

# On the target machine:
git clone /path/to/NtupleAnalyzer_efficiency.bundle NtupleAnalyzer
cd NtupleAnalyzer
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh
```

Copy the parquet tree with `rsync` or an equivalent site-local copy command:

```bash
rsync -av \
  --include='*/' --include='*.parquet' --include='*.json' --include='*.csv' --exclude='*' \
  /eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/efficiency_HLTv2/merged_yieldcorr_20260601/ \
  <target>:/scratch/$USER/merged_yieldcorr_20260601/
```

If running corrected-yield fits on the target, also copy:

```text
/eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/merged/jjp_data_selected.root
```

Then validate the transfer with a quick parquet read before launching the full
fit:

```bash
python3 - <<'PY'
import os
from pathlib import Path
import pandas as pd
base = Path(f"/scratch/{os.environ['USER']}/merged_yieldcorr_20260601")
for sample in ['JJP_DPS1', 'JJP_DPS2_CS', 'JJP_DPS2_G', 'JJP_SPS_CS', 'JJP_SPS_G']:
    frame = pd.read_parquet(base / sample / 'efficiency_maps.parquet')
    rows = frame[(frame['map_type'] == 'correlated_3d') & (frame['step'] == 'Pri_assocPVPass')]
    print(sample, len(rows), rows['efficiency'].mean())
PY
```

### Output products

**Per-file** (`<sample>/`):
- `efficiency_maps.parquet` — cumulative step counts by (pT, y) bin
- `gen_systems.parquet` — gen-level kinematics per event + `n_gen_jpsi`, `n_gen_phi`
- `event_step_flags.parquet` — per-event step flags, per-object fiducial flags, best-reco-candidate columns
- `cutflow.csv` — step-by-step cutflow

**Derived** (`<sample>/derived/`):
- `acceptance_maps.parquet` / `.csv` — fiducial_acceptance / full_gen
- `conditional_efficiency_maps.parquet` / `.csv` — per-step conditional (each step / previous)
- `per_object_acceptance_maps.parquet` / `.csv` — per-object decomposed acceptance
- `stacked_jpsi_acceptance_maps.parquet` / `.csv` — lead+sublead combined
- `stacked_jpsi_efficiency_maps.parquet` / `.csv` — lead+sublead per-step
- `plots/` — CMS-style heatmaps (see AGENTS.md for full directory structure)

### Binning

| Axis | Edges |
|------|-------|
| J/ψ pT | 6.0, 10.0, 15.0, 20.0, 30.0, 50.0, 100.0 GeV |
| φ pT | 4.0, 6.0, 10.0, 20.0, 50.0 GeV |
| \|y\| | 0.0, 0.6, 1.2, 1.8, 2.4 |

### HLT triggers

- `HLT_Dimuon0_Jpsi3p5_Muon2_v` — 3 muons (dimuon J/ψ + extra muon pT > 2)
- `HLT_DoubleMu4_3_LowMass_v` — 2 muons (pT > 4 and 3 GeV)

The `hlt_muon_matched` step requires either a J/ψ dimuon pair matched (2-muon case) or one J/ψ pair + ≥3 of 4 muons matched (3-muon case).

### Candidate handling

**Data:** single best candidate per event by `sqrt(pt1² + pt2² + pt3²)` score.  
**MC efficiency:** "any matched candidate" OR logic — event passes if ≥1 reco candidate matches the gen system.  
**Gen system:** 2 highest-pT J/ψ + 1 highest-pT φ (extra gen φ mesons present in ~1.8% of events).  
**Response matrix:** best-by-quality-score candidate stored in `reco_best_*` columns for migration studies.

### Condor

HTCondor sharded efficiency jobs:
```bash
# Prepare shard lists
python3 prepare_efficiency_shards.py --samples JJP_DPS2_CS --shards-per-sample 200

# Submit
cd condor && ./submit.sh jjp_efficiency
```

## 技术实现

- `uproot`
  - 用于 ntuple schema/文件检查
- `ROOT RDataFrame`
  - 用于 merge + cut + Snapshot
  - 用于 weighted histogram 批量绘制
- 多线程
  - `merge_apply_cuts.py` 和 `plot_weighted_distributions.py` 支持 `-j/--jobs`
- `RooFit + RooStats::SPlot`
  - J/psi: CrystalBall + Gaussian，背景 Exponential
  - Phi: Voigtian，背景二次 Chebychev
  - Ups: 1S/2S/3S 双侧 CrystalBall 组合，背景二次 Chebychev
  - JJY MC: `sel_Jpsi_1_mass`, `sel_Jpsi_2_mass`, `sel_Ups_mass` 三维模型，`signal_sw = yield_sss_sw`

## 本地小规模测试

Merge / fit / plot 链路：

```bash
python3 merge_apply_cuts.py --channel JYP --dataset data \
  -i /eos/user/c/chiw/JpsiUpsPhi/merged_rootNtuple/ParkingDoubleMuonLowMass0_Run2022Cv1.root \
  -n 10000 -j 1 -o /tmp/chiw/jyp_data_test_selected.root

python3 fit_splot.py --channel JYP --dataset data \
  -i /tmp/chiw/jyp_data_test_selected.root \
  -o /tmp/chiw/jyp_data_test_weighted.root \
  --plot-dir /tmp/chiw/jyp_fit_plots -j 1

python3 plot_weighted_distributions.py --channel JYP --dataset data \
  -i /tmp/chiw/jyp_data_test_weighted.root \
  -o /tmp/chiw/jyp_weighted_plots -j 1
```

Efficiency 链路：

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh

# Run single-file efficiency test
python3 run_efficiency.py --analysis-mode JpsiJpsiPhi \
  --output-dir test_output --max-files 1 --samples JJP_DPS2_CS

# Build derived products + plots
python3 build_derived_efficiency.py --input-dir test_output
```
