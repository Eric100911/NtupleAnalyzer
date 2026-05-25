# NtupleAnalyzer assocPV Workflow

这个包现在按 assocPV merge/fit/plot 和 JJP efficiency 工作流运行。公开 channel 名称固定为：

- `JJP`: `J/psi + J/psi + phi`
- `JYP`: `J/psi + Upsilon + phi`
- `JJY`: `J/psi + J/psi + Upsilon`

`JUP` 和 `JJU` 不作为 CLI channel 名称使用；外部 EOS/XRootD 目录里已有的 `JUP_*` 或 `JpsiUpsPhi` 字符串只是存储命名。

主分析按 3 步运行：

1. `merge_apply_cuts.py`
   合并全部 ntuple，做 assocPV 动力学 cut，事件内选最佳候选，输出带原始 branch 和统一 `sel_*` 标量分支的 ROOT 文件。
2. `fit_splot.py`
   对 cut 后样本做质量拟合和 `sPlot`，输出拟合图，并把 `signal_sw` 与各个 yield 的 sWeight 回写到 ROOT 文件。
3. `plot_weighted_distributions.py`
   用 `signal_sw` 为权重绘制所有 `sel_*` 物理量分布，并合并原有关联图功能。

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

- [merge_apply_cuts.py](/afs/cern.ch/user/x/xcheng/condor/CMSSW_15_0_15/src/NtupleAnalyzer/merge_apply_cuts.py)
- [fit_splot.py](/afs/cern.ch/user/x/xcheng/condor/CMSSW_15_0_15/src/NtupleAnalyzer/fit_splot.py)
- [plot_weighted_distributions.py](/afs/cern.ch/user/x/xcheng/condor/CMSSW_15_0_15/src/NtupleAnalyzer/plot_weighted_distributions.py)
- [ntuple_pipeline_common.py](/afs/cern.ch/user/x/xcheng/condor/CMSSW_15_0_15/src/NtupleAnalyzer/ntuple_pipeline_common.py)

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

HTCondor 只建议用于第 1 步 merge。

- MC merge:
  - `condor/jjp_mc.sub`
  - `condor/jyp_mc.sub`
  - `condor/jjy_mc.sub`
- DATA merge:
  - `condor/jjp_data.sub`
  - `condor/jyp_data.sub`

提交辅助脚本仍然是：

```bash
cd condor
./submit.sh jyp_mc --mode DPS_3
./submit.sh jjy_mc --mode all --jobs 1
./submit.sh jjp_data
```

## JJP efficiency

JJP acceptance/efficiency uses full-GEN ntuples directly, not merged selected ROOT files. The first supported mode is `JpsiJpsiPhi`.

```bash
./run_assoc_efficiency.sh \
  --input-files root://cceos.ihep.ac.cn///eos/ihep/cms/store/user/xcheng/MC_Production_v3/output/JJP_DPS1/0/output_ntuple.root \
  --sample-name JJP_DPS1_smoke \
  --skip-plots \
  --output-dir /tmp/chiw/jjp_eff_smoke
```

Full discovery defaults to:

```bash
./run_assoc_efficiency.sh \
  --samples JJP_DPS1,JJP_DPS2_CS,JJP_DPS2_G,JJP_SPS_CS,JJP_SPS_G \
  --output-dir /tmp/chiw/jjp_efficiency_v1
```

Outputs include `gen_systems.parquet`, `event_step_flags.parquet`, `efficiency_counts.parquet`, `efficiency_maps.parquet`, `cutflow.csv`, per-sample manifests, and optional CMS-style efficiency plots.

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

已在本地完成以下链路测试：

```bash
python3 merge_apply_cuts.py --channel JYP --dataset mc --sample DPS_3 \
  --input-dir /afs/cern.ch/user/x/xcheng/condor/JUP_DPS3_0_output_ntuple.root \
  -n 200 -j 1 -o /tmp/xcheng/jyp_mc_test_selected.root

python3 merge_apply_cuts.py --channel JJP --dataset mc --sample DPS_2 \
  --input-dir /afs/cern.ch/user/x/xcheng/condor/JJP_DPS2_0_output_ntuple.root \
  -n 200 -j 1 -o /tmp/xcheng/jjp_mc_test_selected.root

python3 merge_apply_cuts.py --channel JYP --dataset data \
  --input-dir /eos/user/x/xcheng/JpsiUpsPhi/merged_rootNtuple/ParkingDoubleMuonLowMass0_Run2022Cv1.root \
  -n 10000 -j 1 -o /tmp/xcheng/jyp_data_test_selected.root

python3 fit_splot.py --channel JYP --dataset data \
  -i /tmp/xcheng/jyp_data_test_selected.root \
  -o /tmp/xcheng/jyp_data_test_weighted_v2.root \
  --plot-dir /tmp/xcheng/jyp_fit_plots_v2 -j 1

python3 plot_weighted_distributions.py --channel JYP --dataset data \
  -i /tmp/xcheng/jyp_data_test_weighted.root \
  -o /tmp/xcheng/jyp_weighted_plots -j 1
```

说明：

- merge 阶段在 data/MC 小样本上都已跑通。
- fit 和 plot 链路已经打通，但在小统计样本上 `RooFit` 仍会出现明显的数值 warning，正式跑大样本时需要再根据实际统计量调一轮初值和参数范围。
