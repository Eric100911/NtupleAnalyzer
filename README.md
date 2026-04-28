# Ntuple Angular Correlation Analysis

Ntuple数据的角度关联和运动学分析工具，用于分析重建后的 J/ψ+J/ψ+φ (JJP)、J/ψ+Υ+φ (JUP) 和 J/ψ+J/ψ+Υ(1S) (JJY) 过程。

## 文件结构

```
NtupleAnalyzer/
├── analyze_ntuple_JJP.py    # JJP分析主程序
├── analyze_ntuple_JUP.py    # JUP分析主程序
├── analyze_ntuple_JJY.py    # JJY MC分析主程序
├── plot_ntuple_results.py   # 绘图脚本
├── run_jjp_analysis.sh      # JJP Data运行脚本
├── run_jup_analysis.sh      # JUP Data运行脚本
├── run_jjp_mc_ntuple.sh     # JJP MC运行脚本
├── run_jup_mc_ntuple.sh     # JUP MC运行脚本
├── run_jjy_mc_ntuple.sh     # JJY MC运行脚本
├── run_all.sh               # 同时运行JJP和JUP
├── check_proxy.sh           # VOMS代理检查脚本
├── condor/                  # HTCondor配置目录
│   ├── submit.sh            # 作业提交管理脚本
│   ├── run_wrapper.sh       # HTCondor作业包装脚本
│   ├── jup_mc.sub           # JUP MC提交配置
│   ├── jjp_mc.sub           # JJP MC提交配置
│   ├── jup_data.sub         # JUP Data提交配置
│   ├── jjp_data.sub         # JJP Data提交配置
│   └── logs/                # 作业日志目录
├── output/                  # 输出目录
│   ├── jjp_ntuple_correlations.root
│   ├── jup_ntuple_correlations.root
│   ├── plots_JJP/
│   └── plots_JUP/
└── README.md
```

## 数据源

### JJP (J/ψ + J/ψ + φ)
- **路径**: `/eos/user/x/xcheng/JpsiJpsiPhi_muon_pt_cut/merged_rootNtuple/`
- **Tree**: `mkcands/X_data`
- **粒子**: J/ψ₁, J/ψ₂, φ

### JUP (J/ψ + Υ + φ)
- **路径**: `/eos/user/x/xcheng/JpsiUpsPhi/merged_rootNtuple/`
- **Tree**: `mkcands/X_data`
- **粒子**: J/ψ, Υ, φ

### JJY (J/ψ + J/ψ + Υ(1S))
- **DPS_1路径**: `/eos/user/c/chiw/JpsiJpsiUps/MC_samples/rootNtuple_refactor/DPS-Jpsi-JpsiY/filter_JpsiPtMin4p0_YPtMin6p0/`
- **DPS_2路径**: `/eos/user/c/chiw/JpsiJpsiUps/MC_samples/rootNtuple_refactor/DPS-JpsiJpsi-Y/filter_JpsiPtMin4p0_YPtMin6p0/`
- **Tree**: `mkcands/X_data`
- **粒子**: J/ψ₁, J/ψ₂, Υ(1S)
- **可用模式**: `DPS_1`, `DPS_2` (`SPS`保留；不接受裸`DPS`)

## 事件选择 (Cuts)

### JJP 选择条件
| 变量 | 条件 |
|------|------|
| J/ψ 质量 | 2.9 - 3.3 GeV |
| φ 质量 | 0.99 - 1.10 GeV |
| J/ψ pT | > 3.0 GeV |
| φ pT | > 2.0 GeV |
| J/ψ 顶点概率 | > 0.05 |
| φ 顶点概率 | > 0.05 |
| φ K介子 pT | > 2.0 GeV |
| J/ψ Muon ID | soft (默认) |

### JUP 选择条件
| 变量 | 条件 |
|------|------|
| J/ψ 质量 | 2.9 - 3.3 GeV |
| Υ 质量 | 8.5 - 11.4 GeV |
| φ 质量 | 0.99 - 1.10 GeV |
| J/ψ pT | > 3.0 GeV |
| Υ pT | > 4.0 GeV |
| φ pT | > 2.0 GeV |
| J/ψ 顶点概率 | > 0.05 |
| Υ 顶点概率 | > 0.10 |
| φ 顶点概率 | > 0.05 |
| φ K介子 pT | > 2.0 GeV |
| J/ψ Muon ID | soft (默认) |
| Υ Muon ID | tight (默认) |

### JJY 选择条件
| 变量 | 条件 |
|------|------|
| J/ψ₁, J/ψ₂ 质量 | 2.9 - 3.3 GeV |
| Υ(1S) 质量 | 8.5 - 11.4 GeV |
| J/ψ pT | > 3.0 GeV |
| Υ pT | > 4.0 GeV |
| J/ψ 顶点概率 | > 0.05 |
| Υ 顶点概率 | > 0.10 |
| J/ψ Muon ID | soft (默认) |
| Υ Muon ID | tight (默认) |
| Muon重用检查 | 6个候选muon index必须互不重复 |

JJY会为以下4种vertexing选择分别输出一整套直方图和图片：
- `no_vertex`: 不加额外六体顶点选择
- `pri_valid`: `Pri_fitValid` 或 `Pri_VtxValid` 为真
- `pri_vtxprob_gt_0p005`: `Pri_VtxProb > 0.005`
- `same_mu_vertex`: 候选使用的6个muon具有相同且非负的 `muVertexId`

每套JJY输出都包含主要共振质量谱：
- `m(μ⁺μ⁻)` for `Jpsi_1`
- `m(μ⁺μ⁻)` for `Jpsi_2`
- 合并的 `J/ψ₁ + J/ψ₂` dimuon质量谱
- `m(μ⁺μ⁻)` for `Υ(1S)`

### Multi-candidate 选择
对于每个事件中的多个候选，选择 pT score 最高的候选：
```
score = sqrt(pT₁² + pT₂² + pT_φ²)
```

## 使用方法

### 快速开始

```bash
cd /eos/user/x/xcheng/CMSSW_14_0_18/src/NtupleAnalyzer

# 运行JJP分析
./run_jjp_analysis.sh

# 运行JUP分析
./run_jup_analysis.sh

# 运行JJY MC分析 (默认DPS_1，单进程)
./run_jjy_mc_ntuple.sh -n 10000 -j 1

# 同时运行两个分析
./run_all.sh
```

### JJP 分析

```bash
# 基本用法
python3 analyze_ntuple_JJP.py

# 限制处理事件数（用于测试）
python3 analyze_ntuple_JJP.py -n 10000

# 指定输出文件
python3 analyze_ntuple_JJP.py -o my_output.root

# 修改Muon ID要求
python3 analyze_ntuple_JJP.py --muon-id tight
python3 analyze_ntuple_JJP.py --muon-id none  # 不做Muon ID要求
```

### JUP 分析

```bash
# 基本用法
python3 analyze_ntuple_JUP.py

# 限制处理事件数
python3 analyze_ntuple_JUP.py -n 10000

# 自定义Muon ID
python3 analyze_ntuple_JUP.py --jpsi-muon-id soft --ups-muon-id tight
python3 analyze_ntuple_JUP.py --jpsi-muon-id none --ups-muon-id none
```

### JJY MC 分析

```bash
# 直接读取一个EOS目录，递归读取所有ROOT ntuple文件
python3 analyze_ntuple_JJY.py \
  -i /eos/user/c/chiw/JpsiJpsiUps/MC_samples/rootNtuple_refactor/DPS-Jpsi-JpsiY/filter_JpsiPtMin4p0_YPtMin6p0/ \
  -n 10000 -j 1

# 指定输入目录和输出
python3 analyze_ntuple_JJY.py \
  -i /eos/user/c/chiw/JpsiJpsiUps/MC_samples/rootNtuple_refactor/DPS-JpsiJpsi-Y/filter_JpsiPtMin4p0_YPtMin6p0/ \
  -o output/jjy_mc_DPS_2_correlations.root \
  --jpsi-muon-id soft --ups-muon-id tight -j 1

# 调整J/ψ和Υ dimuon质量谱binning
python3 analyze_ntuple_JJY.py \
  --jpsi-mass-bins 30 --jpsi-mass-min 2.8 --jpsi-mass-max 3.4 \
  --ups-mass-bins 40 --ups-mass-min 8.5 --ups-mass-max 10.5

# 同时运行分析和四套vertexing选择图
./run_jjy_mc_ntuple.sh -m DPS_1 -n 10000 -j 1 --jpsi-mass-bins 30 --ups-mass-bins 40
./run_jjy_mc_ntuple.sh -m DPS_2 -n 10000 -j 1 --jpsi-mass-bins 30 --ups-mass-bins 40
```

### 绘图

```bash
# JJP绘图
python3 plot_ntuple_results.py -i output/jjp_ntuple_correlations.root -o plots_JJP -p JJP

# JUP绘图
python3 plot_ntuple_results.py -i output/jup_ntuple_correlations.root -o plots_JUP -p JUP

# JJY绘图，输出目录下会生成四个vertexing选择子目录
python3 plot_ntuple_results.py -i output/jjy_mc_DPS_1_correlations.root -o plots_JJY_DPS_1 -p JJY
```

## 输出直方图

### 角度关联
- `h_dy_*`: Δy (快度差) 分布
- `h_dphi_*`: Δφ (方位角差) 分布
- `h2_dy_dphi_*`: 2D Δy vs Δφ 关联图

### 运动学分布
- `h_*_pt`: pT 分布
- `h_*_eta`: η (伪快度) 分布
- `h_*_y`: y (快度) 分布
- `h_*_phi`: φ (方位角) 分布

### 不变质量
- `h_mass_*`: 两体/三体不变质量分布

## 输出图像

每个过程生成以下图像：
- `delta_y_comparison_*.pdf/png`: Δy 比较图
- `delta_phi_comparison_*.pdf/png`: Δφ 比较图
- `correlation_2d_*_*.pdf/png`: 单独的2D关联图
- `correlation_2d_all_*.pdf/png`: 组合2D关联图
- `pt_distributions_*.pdf/png`: pT 分布
- `eta_distributions_*.pdf/png`: η 分布
- `rapidity_distributions_*.pdf/png`: y 分布
- `phi_distributions_*.pdf/png`: φ 分布
- `invariant_mass_*.pdf/png`: 不变质量分布

## 参考

- 事件选择参考: `NPSExtraction/sPlotFit/run_mass_fit_JJP.py`, `run_mass_fit_JUP.py`
- 角度关联计算参考: `JJPMCAnalyzer/analyze_gen_correlations.py`
- 绘图风格参考: `JJPMCAnalyzer/plot_results.py`

---

## HTCondor 批量作业提交

### 准备工作

1. **设置VOMS代理** (用于xrootd访问T2_CN_Beijing等远程存储):
```bash
# 初始化代理 (有效期7天)
voms-proxy-init --voms cms --valid 168:00

# 确认HTCondor可读取的现有代理路径
voms-proxy-info --path

# 检查代理状态
./check_proxy.sh
```

2. **进入condor目录**:
```bash
cd condor/
```

### 使用submit.sh提交作业

`submit.sh` 是一个便捷的作业提交管理脚本：

```bash
# 查看帮助
./submit.sh --help

# 提交JUP MC分析 (默认DPS_1模式)
./submit.sh jup_mc

# 提交JUP MC特定模式
./submit.sh jup_mc --mode SPS
./submit.sh jup_mc --mode DPS_2 --jobs 16

# 提交所有JUP MC模式
./submit.sh jup_mc --mode all

# 提交JJP MC分析
./submit.sh jjp_mc --mode DPS
./submit.sh jjp_mc --mode TPS

# 提交JJY MC分析 (两个完整ntuple目录，单核/单进程)
./submit.sh jjy_mc --mode DPS_1 --jobs 1
./submit.sh jjy_mc --mode DPS_2 --jobs 1
./submit.sh jjy_mc --mode all --jobs 1

# 提交数据分析
./submit.sh jup_data
./submit.sh jjp_data --max-events 100000

# 查看作业状态
./submit.sh --status

# 查看作业历史
./submit.sh --history

# 清理日志文件
./submit.sh --clean

# 试运行 (不实际提交)
./submit.sh jup_mc --mode DPS_1 --dry-run
./submit.sh jjy_mc --mode all --jobs 1 --dry-run
```

### 直接使用condor_submit

也可以直接使用 `condor_submit` 命令：

```bash
# 基本提交
condor_submit jup_mc.sub

# 覆盖默认参数
condor_submit jup_mc.sub MODE=DPS_2 JOBS=16

# 提交JJP MC
condor_submit jjp_mc.sub MODE=TPS

# 提交JJY MC
condor_submit jjy_mc.sub MODE=DPS_1
condor_submit jjy_mc.sub MODE=DPS_2 JOBS=1

# 提交数据分析
condor_submit jup_data.sub MAX_EVENTS=100000
condor_submit jjp_data.sub MUON_ID=tight
```

### 作业配置参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `MODE` | MC模式 (JUP: SPS/DPS_1/DPS_2/DPS_3/TPS, JJP: DPS/TPS, JJY: DPS_1/DPS_2) | DPS_1 / DPS |
| `JOBS` | 分析脚本并行进程数 (JJY Condor默认单进程) | 8 / JJY: 1 |
| `MAX_EVENTS` | 最大处理事件数 (-1=全部) | -1 |
| `MUON_ID` | JJP muon ID | soft |
| `JPSI_MUON_ID` | JUP J/psi muon ID | soft |
| `UPS_MUON_ID` | JUP Upsilon muon ID | tight |

### 资源配置

默认资源配置 (可在.sub文件中修改):

| 资源 | MC作业 | 数据作业 |
|------|--------|----------|
| 内存 | 48 GB (JJY: 16 GB) | 64 GB |
| CPU核心 | 8 (JJY: 1) | 16 |
| 磁盘 | 10 GB | 20 GB |
| 时间限制 | workday (8h) | workday (8h) |

### 作业管理

```bash
# 查看当前作业
condor_q

# 查看详细信息
condor_q -long <job_id>

# 取消作业
condor_rm <job_id>

# 取消所有作业
condor_rm $(whoami)

# 查看作业日志
tail -f condor/logs/jup_mc/jup_mc_DPS_1_*.out

# 检查错误
cat condor/logs/jup_mc/jup_mc_DPS_1_*.err
```

### Job Flavour (时间限制)

| Flavour | 最大运行时间 |
|---------|-------------|
| espresso | 20 分钟 |
| microcentury | 1 小时 |
| longlunch | 2 小时 |
| workday | 8 小时 |
| tomorrow | 1 天 |
| testmatch | 3 天 |
| nextweek | 1 周 |

修改时间限制:
```bash
./submit.sh jup_mc --mode all --flavor tomorrow
```

### 输出文件

作业完成后，输出文件位于:
- ROOT文件: `output/jup_mc_<MODE>_correlations.root`
- 图像: `output/plots_JUP_MC_<MODE>/`
- 日志: `condor/logs/<analysis_type>/`
