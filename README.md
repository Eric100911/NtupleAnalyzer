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
4. Efficiency pipeline (`run_efficiency.py` → `merge_efficiency_shards.py` → `build_derived_efficiency.py` → `compute_efficiency_corrected_yield.py`)
   从 GEN 级 ntuple 直接计算 J/ψ+J/ψ+φ 的 acceptance 和逐步 conditional efficiency，输出 binned maps 和 CMS-style plots，最终计算 efficiency-corrected signal yield。

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
  - **本地已合并 MC**: `/home/storage29/users/chiwang/JpsiJpsiPhi/MC_samples/selected-merged-v3/`
    - `jjp_mc_dps_1_selected.root` (68,893 events), `jjp_mc_dps_2_cs_selected.root` (32,533)
    - `jjp_mc_dps_2_g_selected.root` (966), `jjp_mc_sps_cs_selected.root` (7,977)
    - `jjp_mc_sps_g_selected.root` (748)
    - 已过 GEN-match, `sel_*` 分支, tree `"selected"`, 无 sWeights（全信号, weight=1）
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

### 预效率 pipeline (merge → sPlot → 画图)

| 脚本 | 用途 |
|------|------|
| [ntuple_pipeline_common.py](ntuple_pipeline_common.py) | 共享 channel config, input discovery, C++ RDataFrame helpers |
| [merge_apply_cuts.py](merge_apply_cuts.py) | 合并 + assocPV cuts + best-candidate selection |
| [fit_splot.py](fit_splot.py) | 质量拟合 + sPlot sWeights |
| [plot_weighted_distributions.py](plot_weighted_distributions.py) | sWeight-weighted 运动学分布 + pair Δy/Δφ 2D 关联图 |

### MC-Data 一致性检查

| 脚本 | 用途 |
|------|------|
| [plot_kinematics_jjp.py](plot_kinematics_jjp.py) | **Pre-efficiency kinematics**: sWeight data-only + data-MC overlay（5 个 MC 样本叠加，shape-normalized 比较） |
| [plot_data_mc_comparison.py](plot_data_mc_comparison.py) | **单样本 data/MC 比较**: 双面板（分布 + Data/MC ratio），带 χ²/ndf 兼容性检验和 p-value |
| [add_mc_weights.py](add_mc_weights.py) | 给 GEN-matched MC 文件加 `signal_sw=1.0` 分支（RDataFrame Snapshot）— 供 plot_data_mc_comparison.py 使用 |

### Efficiency 计算 pipeline

| 脚本 | 用途 |
|------|------|
| [run_efficiency.py](run_efficiency.py) | 效率计算入口 |
| [prepare_efficiency_shards.py](prepare_efficiency_shards.py) | 准备 Condor shard 列表 |
| [merge_efficiency_shards.py](merge_efficiency_shards.py) | 合并 shard 输出 |
| [rebuild_efficiency_maps.py](rebuild_efficiency_maps.py) | 从已有 gen/event parquet 重建 efficiency maps（非覆盖式） |
| [build_derived_efficiency.py](build_derived_efficiency.py) | 构建 derived 产品: acceptance, conditional, per-object, stacked, pair-level maps + plots；`--plot-scope stacked-jpsi` 只画 stacked J/ψ |
| [build_systematic_uncertainty.py](build_systematic_uncertainty.py) | 计算 subprocess envelope systematics（ratio, envelope half-width, max-pull） |
| [build_response_classification.py](build_response_classification.py) | 构建 response matrix 分类用于效率修正诊断 |
| [print_cutflow.py](print_cutflow.py) | 打印格式化的 cutflow 表格（text / LaTeX / CSV） |

### Efficiency 修正与 Yield

| 脚本 | 用途 |
|------|------|
| [apply_efficiency_corrections.py](apply_efficiency_corrections.py) | 给 ROOT tree 加 efficiency 修正权重分支 |
| [compute_efficiency_corrected_yield.py](compute_efficiency_corrected_yield.py) | **主入口**: 计算 efficiency-corrected signal yield，支持 factorized 和 legacy-correlated 两种模式 |

### 诊断与测试

| 脚本 | 用途 |
|------|------|
| [check_candchoice_closure.py](check_candchoice_closure.py) | 候选选择 closure 检查 |
| [classify_response_events.py](classify_response_events.py) | 按 response migration pattern 分类事件 |
| [test_acceptance_factorization.py](test_acceptance_factorization.py) | 逐 bin closure 检验 acceptance 因子化假设 (A_direct vs A_factorized) |
| [quantify_scand_factorization.py](quantify_scand_factorization.py) | 量化 S_cand 因子化程度 |
| [test_closure_cli.py](test_closure_cli.py) | CLI closure tests |
| [test_efficiency_corrections.py](test_efficiency_corrections.py) | 效率修正单元测试 |
| [test_efficiency_schema.py](test_efficiency_schema.py) | 效率数据产品 schema 验证 |
| [test_efficiency_systematics.py](test_efficiency_systematics.py) | 系统误差计算单元测试 |
| [test_factorized_maps.py](test_factorized_maps.py) | Factorized map 构建测试 |
| [test_scand_factorization.py](test_scand_factorization.py) | SCand 因子化测试 |

### 分析与研究

| 脚本 | 用途 |
|------|------|
| [analyze_ntuple_JJP.py](analyze_ntuple_JJP.py) | JJP ntuple 通用分析 |
| [analyze_ntuple_JJP_window.py](analyze_ntuple_JJP_window.py) | JJP mass window 研究 |
| [analyze_ntuple_JYP.py](analyze_ntuple_JYP.py) | JYP ntuple 分析 |
| [analyze_ntuple_JJY.py](analyze_ntuple_JJY.py) | JJY ntuple 分析 |
| [compare_bbb_splot_sideband.py](compare_bbb_splot_sideband.py) | sPlot 与 sideband subtraction 比较 |
| [study_splot_sideband_vertex_cuts.py](study_splot_sideband_vertex_cuts.py) | Vertex cut 对 sPlot sideband 的影响 |
| [plot_dionia_vtx_ctau_shape_study.py](plot_dionia_vtx_ctau_shape_study.py) | Vertex/ctau 形状研究 |
| [plot_vertex_cut_pileup_study.py](plot_vertex_cut_pileup_study.py) | Vertex cut vs pileup 研究 |
| [plot_ntuple_results.py](plot_ntuple_results.py) | 通用 ntuple 结果画图 |
| [apply_genmatch_to_merged.py](apply_genmatch_to_merged.py) | 对已合并 MC 文件回溯应用 GEN-match 过滤 |

### Efficiency workflow 模块 ([efficiency_workflow/](efficiency_workflow/))

| 模块 | 用途 |
|------|------|
| `efficiency.py` | 核心效率计算: per-object step columns, event-level steps, EfficiencyBinning, build_efficiency_counts(), build_cutflow(), process_efficiency_file() |
| `corrections.py` | 效率修正 map: EfficiencyCorrectionMap (correlated 3D/5D), FactorizedCorrectionMap (per-object × event-level), vectorized lookups |
| `closure.py` | Closure tests: GEN vs corrected-reco yields |
| `plotting.py` | 效率画图: 2D heatmaps, ratio plots (sample/nominal), envelope half-width, max-pull, systematic uncertainty, yield comparison bar charts |
| `products.py` | Derived 效率产品: acceptance maps, conditional maps, pair-level maps, per-object acceptance, stacked J/ψ maps |
| `yield_correction.py` | 效率修正 yield: 3D mass fit × per-event efficiency weights, per-sample systematic envelope |
| `build_factorized_maps.py` | 构建 factorized 修正 maps: per-object + event-level factors |
| `scand_factorization.py` | SCand 因子化诊断 |
| `config.py` | 配置 dataclasses: StudyConfig, OfflineSelectionConfig, MassStudyConfig, CmsPlotStyleConfig |
| `io.py` | I/O 工具: ensure_dir, read/write_json, read/write_parquet |
| `systematics.py` | 系统误差: envelope half-width, max-pull, ratio 计算 |
| `truth.py` | GEN-level truth helpers |
| `cli_efficiency.py` | 效率计算 CLI: 文件 staging (xrootd→local), 逐文件处理, 合并, derived 产品 |

## MC-Data 一致性检查 (MC-Data Agreement)

有三个层次的一致性检查。Level 1 和 Level 2 使用 `selected-merged-v3` MC 样本；Level 3 是 MC-MC 比较。

### 完整 data-MC 比较流程

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh

# 1. sPlot 拟合 data → 得到 signal_sw 分支
python3 fit_splot.py --channel JJP --dataset data \
  -i ../jjp_data_selected.root \
  -o plots_kinematics/temp/jjp_data_weighted.root \
  --plot-dir plots_kinematics/temp/fit -j 4

# 2. 给 MC 文件加 signal_sw=1.0（全信号，weight=1）
python3 add_mc_weights.py

# 3. 创建符号链接（plot_kinematics_jjp.py 需要 JJP_DPS1_merged.root 等名字）
mkdir -p plots_kinematics/temp/mc_links && cd plots_kinematics/temp/mc_links
MC=/home/storage29/users/chiwang/JpsiJpsiPhi/MC_samples/selected-merged-v3
ln -sf $MC/jjp_mc_dps_1_selected.root JJP_DPS1_merged.root
ln -sf $MC/jjp_mc_dps_2_cs_selected.root JJP_DPS2_CS_merged.root
ln -sf $MC/jjp_mc_dps_2_g_selected.root JJP_DPS2_G_merged.root
ln -sf $MC/jjp_mc_sps_cs_selected.root JJP_SPS_CS_merged.root
ln -sf $MC/jjp_mc_sps_g_selected.root JJP_SPS_G_merged.root
cd ../../..

# 4a. Type A: 全 MC 叠加（30 个运动学变量，shape-normalized）
python3 plot_kinematics_jjp.py --mode comparison \
  --weighted-data plots_kinematics/temp/jjp_data_weighted.root \
  --mc-dir plots_kinematics/temp/mc_links \
  -o plots_kinematics --skip-splot --normalize shape

# 4b. Type B: 单样本 ratio panel（χ²/ndf + p-value）
# 仅对高统计量样本：DPS_1, DPS_2_CS, SPS_CS
for S in DPS_1 DPS_2_CS SPS_CS; do
  s_lower=$(echo $S | tr '[:upper:]' '[:lower:]')
  python3 plot_data_mc_comparison.py --channel JJP --mc-sample "$S" \
    --data-input plots_kinematics/temp/jjp_data_weighted.root \
    --mc-input plots_kinematics/temp/jjp_mc_${s_lower}_weighted.root \
    --data-weight-branch signal_sw --mc-weight-branch signal_sw \
    --normalize shape -o plots_kinematics/comparison_ratio/$S
done
```

### Level 1: Pre-Efficiency 运动学叠加 (`plot_kinematics_jjp.py`)

sWeight data 与全部 5 个 MC 样本的归一化形状比较：
- **Data**: sWeight events（黑色 errorbar 点）
- **MC**: 5 个子过程样本叠加（彩色 step histograms: DPS_1, DPS_2_CS, DPS_2_G, SPS_CS, SPS_G）
- **归一化**: 默认 shape-normalized（单位积分），也可用 `--normalize yield`
- **变量**: pT, y/η, φ for J/ψ, φ, J/ψ muons, φ kaons; 外加 J/ψ 和 φ 的 |y|
- **输出**: `plots_kinematics/comparison/`（30 PDF + 30 PNG）
- **无 ratio panel 或 χ²** — 纯视觉叠加检查形状一致性
- **MC 文件命名**: 脚本内 `MC_SAMPLE_FILES` dict 期待 `JJP_DPS1_merged.root` 等名字。
  用 `--mc-dir` 指向包含符号链接的目录，或直接修改 dict。
- **MC 权重**: `load_branch_mc()` 内部使用 weight=1 — 不需要 weight 分支。

### Level 2: 单样本 Data/MC + Ratio Panel (`plot_data_mc_comparison.py`)

sWeight data 与单个 MC 样本的详细比较，带定量指标：
- **布局**: 双面板（上: 分布叠加，下: Data/MC ratio）
- **指标**: χ²/ndf + p-value（逐 bin 兼容性检验）
- **Ratio panel**: Data/MC 带 error bars; 参考线 = 1.0; y-range [0.4, 1.6]
- **特殊处理**: ctau 分布用 log-scale y-axis
- **MC weight 分支**: 此脚本要求 MC tree 中有 weight 分支。
  用 `add_mc_weights.py`（RDataFrame Snapshot）加 `signal_sw=1.0`。
- **输出**: `plots_kinematics/comparison_ratio/{sample}/`（每样本 ~105 PDF + 105 PNG）
- **典型目标**: DPS_1, DPS_2_CS, SPS_CS（DPS_2_G 和 SPS_G 统计量太低不建议）

### Level 3: Efficiency Map 比率/Pull Plots (`efficiency_workflow/plotting.py` + `build_systematic_uncertainty.py`)

MC 样本之间的效率 map 比较（纯 MC-MC，不含 data）：
- **Ratio plots**: `ε(sample) / ε(nominal)` 逐 bin → 揭示子过程依赖性
- **Envelope half-width**: 所有样本相对 nominal 的最大偏差
- **Max-pull plots**: `|ε(sample) − ε(nominal)| / √(σ²_sample + σ²_nominal)` → 偏差的统计显著性
- **Yield comparison**: 各样本修正后 yield 的 bar chart

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

The efficiency pipeline computes fiducial acceptance and per-step conditional efficiencies for J/ψ+J/ψ+φ events, binned in meson pT and rapidity. It works directly on GEN-level ntuples (not merged selected ROOT files). Raw per-object maps keep signed rapidity `y`; factorized correction maps and stacked J/ψ derived maps use `(pT, |y|)`.

### Efficiency step schema

**Per-object chains** (self-contained; each resets denominator to total events):

| Object | Steps |
|--------|-------|
| `jpsi_lead` | fiducial → muonRECO → muonID → dimuon |
| `jpsi_sublead` | fiducial → muonRECO → muonID → dimuon |
| `phi` | fiducial → kaonRECO → kaonID → dikaon |

**Event-level chain** (sequential, then parallel):

```
full_gen → s_cand → hlt_event → hlt_muon_matched → four_muon_vtx
                                                          ↓
                          ┌───────────────────────────────┴───────────────────────┐
                          ↓               ↓                ↓                       ↓
                      Pri_fitValid    Pri_fitPass    Pri_assocPVPass    Pri_trackPVPass
```

Each Pri_* step is conditional on `four_muon_vtx` (parallel, not sequential among themselves).

### Pipeline stages

1. **`run_efficiency.py`** — per-file efficiency shard: finds gen J/ψ+J/ψ+φ systems, matches reco candidates, computes cumulative step flags. Supports `--efficiency-backend vectorized|python-loop`, `--max-files N` for testing.
2. **`merge_efficiency_shards.py`** — merges shard outputs into per-sample files.
3. **`build_derived_efficiency.py`** — produces derived maps and plots from merged output. Use `--plot-scope stacked-jpsi` when only the stacked J/ψ `(pT, |y|)` plots are needed.
4. **`build_systematic_uncertainty.py`** — computes subprocess envelope systematics (optional, for yield correction).
5. **`compute_efficiency_corrected_yield.py`** — applies efficiency weights to data and computes corrected signal yield.

### Quick test

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh

# One-file efficiency test
python3 run_efficiency.py --analysis-mode JpsiJpsiPhi \
  --output-dir /tmp/chiw/eff_test --max-files 1 --samples JJP_DPS2_CS --skip-plots

# Build derived products
python3 build_derived_efficiency.py --input-dir /tmp/chiw/eff_test
```

### Stacked J/psi plots only

This mode rebuilds derived parquet/csv products but only renders the stacked
lead+sublead J/psi acceptance and per-object efficiency plots. It skips
cumulative, conditional, pair-level, and systematics plots.

```bash
bash -c 'source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh && \
  python3 build_derived_efficiency.py \
    --input-dir ../merged_efficiency_output_20260601_01 \
    --output-dir stacked_jpsi_pt_absy_only_YYYYMMDD \
    --plot-scope stacked-jpsi --min-plot-total 1'
```

Expected regular output is four PNGs per sample in
`<output>/<sample>/derived/plots/stacked_jpsi/`:
`stacked_jpsi_absy_fiducial_acceptance.png`,
`stacked_jpsi_absy_muonRECO.png`, `stacked_jpsi_absy_muonID.png`, and
`stacked_jpsi_absy_dimuon.png`. Add `--with-uncertainty-plots` only when the
matching QA uncertainty panels are needed.

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

### Correction modes

Two correction strategies are available:

1. **`factorized`** (recommended): Correction weight = 1/∏(ε_per_object · ε_event).
   Each factor is a 2D map in (pT, |y|). Two-tier fallback: fine bins (≥30 MC events)
   → coarse bins (≥50 MC events) → error. Much better statistical precision than
   fully-correlated maps.

   ```text
   w = 1 / [ A(J/ψ₁) · A(J/ψ₂) · A(φ)
             · ε_muReco(J/ψ₁) · ε_muReco(J/ψ₂)
             · ε_muID(J/ψ₁) · ε_muID(J/ψ₂)
             · ε_dimuon(J/ψ₁) · ε_dimuon(J/ψ₂)
             · ε_kaonReco(φ) · ε_kaonID(φ) · ε_dikaon(φ)
             · ε_HLT · ε_4μ_vtx · ε_triOnia ]
   ```

2. **`legacy-correlated`**: Correction weight = 1/ε_correlated_3d.
   Direct lookup in correlated 3D (pT_J/ψ1, pT_J/ψ2, pT_φ) bins. Sparser bins,
   larger statistical fluctuations.

### Efficiency-corrected yield

The JJP corrected-yield workflow fits the selected data once without weights,
then builds one weighted mini-tree per MC subprocess correction and refits each tree.
The nominal central value currently uses `JJP_DPS1`; the systematic is the
subprocess envelope across the configured samples.

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

### Output products

**Per-file** (`<sample>/`):
- `efficiency_maps.parquet` — cumulative step counts; raw `object_2d` rows are binned by `(pT, signed y)`
- `efficiency_counts.parquet` — alias for efficiency_maps
- `gen_systems.parquet` — gen-level kinematics per event + `n_gen_jpsi`, `n_gen_phi`
- `event_step_flags.parquet` — per-event step flags, per-object fiducial flags, best-reco-candidate columns
- `cutflow.csv` — step-by-step cutflow
- `sample_manifest.json` — per-sample metadata

**Derived** (`<sample>/derived/`):
- `acceptance_maps.parquet` — fiducial_acceptance / full_gen
- `conditional_efficiency_maps.parquet` — per-step conditional (each step / previous)
- `per_object_acceptance_maps.parquet` — per-object decomposed acceptance
- `stacked_jpsi_acceptance_maps.parquet` — lead+sublead J/psi combined, direct `(pT, |y|)` with `y_axis == "abs_y"`
- `stacked_jpsi_efficiency_maps.parquet` — lead+sublead J/psi `muonRECO`, `muonID`, `dimuon` per-step maps, direct `(pT, |y|)` with `y_axis == "abs_y"`
- `pair_vertex_*.parquet` — pair-level vertex efficiency
- `plots/` — CMS-style heatmaps (2D efficiency, acceptance)

**Factorized** (`<sample>/factorized/`):
- `acceptance_jpsi.parquet`, `acceptance_phi.parquet` — per-object fiducial acceptance
- `eff_muReco_jpsi.parquet`, `eff_muID_jpsi.parquet`, `eff_dimuon_jpsi.parquet` — J/ψ per-step efficiency
- `eff_kaonReco_phi.parquet`, `eff_kaonID_phi.parquet`, `eff_dikaon_phi.parquet` — φ per-step efficiency
- `s_cand.parquet` — event-level S_cand efficiency

**SCand factorization** (`<sample>/scand_factorization/`):
- Per-stage diagnostic parquet files comparing direct 3-body vs factorized S_cand efficiency

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
- `pandas` + `parquet`
  - Efficiency maps 存储为 parquet 格式
  - 逐 bin 效率值、统计误差、系统误差
- `matplotlib` + `mplhep`
  - CMS style plots（Preliminary label, lumi, energy）
  - 2D efficiency heatmaps, ratio plots, pull plots, yield bar charts

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

MC-Data 一致性检查：

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh

# Step 1: sPlot on data → weighted file
python3 fit_splot.py --channel JJP --dataset data \
  -i ../jjp_data_selected.root \
  -o plots_kinematics/temp/jjp_data_weighted.root \
  --plot-dir plots_kinematics/temp/fit -j 4

# Step 2: Add signal_sw=1.0 to MC files
python3 add_mc_weights.py

# Step 3: Symlinks for MC file naming
mkdir -p plots_kinematics/temp/mc_links && cd plots_kinematics/temp/mc_links
MC=/home/storage29/users/chiwang/JpsiJpsiPhi/MC_samples/selected-merged-v3
for f in $MC/jjp_mc_*_selected.root; do
  target=$(basename $f | sed 's/jjp_mc_//;s/_selected//' | tr '[:lower:]' '[:upper:]')
  ln -sf $f JJP_${target}_merged.root
done
cd ../../..

# Step 4a: Multi-MC overlay (all 5 MC samples vs data, ~30 plots)
python3 plot_kinematics_jjp.py --mode comparison \
  --weighted-data plots_kinematics/temp/jjp_data_weighted.root \
  --mc-dir plots_kinematics/temp/mc_links \
  -o plots_kinematics --skip-splot

# Step 4b: Ratio panel with χ²/ndf for each high-stat sample (~105 plots each)
for S in DPS_1 DPS_2_CS SPS_CS; do
  s_lower=$(echo $S | tr '[:upper:]' '[:lower:]')
  python3 plot_data_mc_comparison.py --channel JJP --mc-sample "$S" \
    --data-input plots_kinematics/temp/jjp_data_weighted.root \
    --mc-input plots_kinematics/temp/jjp_mc_${s_lower}_weighted.root \
    --data-weight-branch signal_sw --mc-weight-branch signal_sw \
    --normalize shape -o plots_kinematics/comparison_ratio/$S
done

# Cutflow table
python3 print_cutflow.py -i ../merged_efficiency_output_20260601_01 -f table
```
