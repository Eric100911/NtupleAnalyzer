# NtupleAnalyzer assocPV Workflow

这个包现在按 3 步工作流运行：

1. `merge_apply_cuts.py`
   合并全部 ntuple，做 assocPV 动力学 cut，事件内选最佳候选，输出带原始 branch 和统一 `sel_*` 标量分支的 ROOT 文件。
2. `fit_splot.py`
   对 cut 后样本做质量拟合和 `sPlot`，输出拟合图，并把 `signal_sw` 与各个 yield 的 sWeight 回写到 ROOT 文件。
3. `plot_weighted_distributions.py`
   用 `signal_sw` 为权重绘制所有 `sel_*` 物理量分布，并合并原有关联图功能。

所有默认输出都写到：

`/eos/user/x/xcheng/learn_MC/NtupleAnalyzer_assocPV`

## 输入路径

- DATA:
  - JJP: `/eos/user/x/xcheng/JpsiJpsiPhi_muon_pt_cut/merged_rootNtuple`
  - JUP: `/eos/user/x/xcheng/JpsiUpsPhi/merged_rootNtuple`
- MC:
  - 基础目录: `/eos/ihep/cms/store/user/xcheng/MC_Production_v2/output`
  - 程序会自动转成 `root://cceos.ihep.ac.cn//eos/ihep/...` 并优先读取 `output_ntuple.root`
  - 默认 proxy: `/afs/cern.ch/user/x/xcheng/x509up_u180107`

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
- JUP:
  - 继承上面的 J/psi、muon、Kaon、Phi cut
  - `Ups mass in [8.5, 11.4]`
  - `abs(y_Ups) < 2.5`

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

JUP data 全流程：

```bash
./run_jup_analysis.sh
```

只跑 merge：

```bash
./run_assoc_merge.sh --channel JJP --dataset data
./run_assoc_merge.sh --channel JUP --dataset mc --sample DPS_3
```

只跑拟合：

```bash
./run_assoc_fit.sh --channel JJP --dataset data
```

只跑加权画图：

```bash
./run_assoc_plots.sh --channel JUP --dataset data
```

## HTCondor

HTCondor 只建议用于第 1 步 merge。

- MC merge:
  - `condor/jjp_mc.sub`
  - `condor/jup_mc.sub`
- DATA merge:
  - `condor/jjp_data.sub`
  - `condor/jup_data.sub`

提交辅助脚本仍然是：

```bash
cd condor
./submit.sh jup_mc --mode DPS_3
./submit.sh jjp_data
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

## 本地小规模测试

已在本地完成以下链路测试：

```bash
python3 merge_apply_cuts.py --channel JUP --dataset mc --sample DPS_3 \
  --input-dir /afs/cern.ch/user/x/xcheng/condor/JUP_DPS3_0_output_ntuple.root \
  -n 200 -j 1 -o /tmp/xcheng/jup_mc_test_selected.root

python3 merge_apply_cuts.py --channel JJP --dataset mc --sample DPS_2 \
  --input-dir /afs/cern.ch/user/x/xcheng/condor/JJP_DPS2_0_output_ntuple.root \
  -n 200 -j 1 -o /tmp/xcheng/jjp_mc_test_selected.root

python3 merge_apply_cuts.py --channel JUP --dataset data \
  --input-dir /eos/user/x/xcheng/JpsiUpsPhi/merged_rootNtuple/ParkingDoubleMuonLowMass0_Run2022Cv1.root \
  -n 10000 -j 1 -o /tmp/xcheng/jup_data_test_selected.root

python3 fit_splot.py --channel JUP --dataset data \
  -i /tmp/xcheng/jup_data_test_selected.root \
  -o /tmp/xcheng/jup_data_test_weighted_v2.root \
  --plot-dir /tmp/xcheng/jup_fit_plots_v2 -j 1

python3 plot_weighted_distributions.py --channel JUP --dataset data \
  -i /tmp/xcheng/jup_data_test_weighted.root \
  -o /tmp/xcheng/jup_weighted_plots -j 1
```

说明：

- merge 阶段在 data/MC 小样本上都已跑通。
- fit 和 plot 链路已经打通，但在小统计样本上 `RooFit` 仍会出现明显的数值 warning，正式跑大样本时需要再根据实际统计量调一轮初值和参数范围。
