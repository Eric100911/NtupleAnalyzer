# JJP 效率、角分布与 φ 来源检查：结果汇总

日期：2026-10-22。本文汇总效率、角分布及 $\phi$ 来源/ctau 调查的已完成结果，按产物与代码版本给出解释。研究对象为 JJP（$J/\psi+J/\psi+\phi$）。

## 结论速览

1. **效率链分母已修正，新版地图与图表已生成。** 对提交 `ed602ad57b80883a948cd91197cec63177f990a3` 的审计表明，旧对象因子的分母使用前一级原始 flag，因子乘积不保证等于累计效率。当前提交 `f9e6c4e6dcaa52cc697dd3acea80b2b9bf678841` 已改为累计对象 mask，并从六样本 merged 输入重新生成 72 个 correction map 文件和 1,380 张 efficiency PNG；产物见[新版效率结果目录](../efficiency_maps_cumulative_20261022/)。
2. **新的文件隔离 closure 给出明确的样本差异。** DPS1 的 factorized/hybrid corrected/GEN 分别为 $0.985/0.984$；SPS_CS 分别为 $0.842/0.942$。SPS_CS 的 hybrid 中心值更接近 1，区间也覆盖 1。两者均使用修正后的当前代码重新构建训练地图，检查的是完整候选存在的事件级选择。
3. **对象间因子化在 joint quality / `s_cand` 级仍有偏差。** holdout 上 direct/predicted 为 DPS1 $1.108$、SPS_CS $1.152$。这与单个对象链内分母是否累计是不同的问题。
4. **角度脚本已修正参考系错误并重算。** 修正后的 selected reco MC 中，$\phi$ 的 $\langle\cos^2\theta_H\rangle$ 为 DPS1 $0.26099\pm0.00104$、SPS_CS $0.23448\pm0.00291$。把 SPS_CS 的 $\phi$ $(p_T,|y|)$ 组成重加权到 DPS1 后，二阶矩变为 $0.25681\pm0.00369$；原约 $8.6\sigma$ 的差异缩至约 $1.1\sigma$（统计误差近似）。
5. **严格匹配后的旧版 MC 中仍有开放重味祖先证据；数据 ctau 正向尾部的信号产额对质量分辨率模型敏感。** 五个旧版 selected MC 的 108,925 个完整 GEN 系统匹配候选中，38 个有 beauty、2,339 个有 charm 祖先证据，其余 106,548 个来源未明。数据 $\phi$ ctau $\geq0.1\,\mathrm{cm}$ 的拟合产额在两种 $\sigma_\phi$ 上限下分别为 $79.1\pm31.6$ 与 $190.6\pm44.9$；这组结果尚不能确定 prompt/nonprompt 比例。

## 一、效率定义与版本顺序

旧构造对每个对象使用原始 flag $F,R,I,D$（fiducial、RECO、ID、dimuon/dikaon），其三个因子为

$$
e_1=\frac{N(F\cap R)}{N(F)},\qquad
e_2=\frac{N(R\cap I)}{N(R)},\qquad
e_3=\frac{N(I\cap D)}{N(I)}.
$$

用于相乘的累计链应定义 $C_0=F$、$C_1=F\cap R$、$C_2=F\cap R\cap I$、$C_3=F\cap R\cap I\cap D$，取 $e_k=N(C_k)/N(C_{k-1})$，于是 $\prod_k e_k=N(C_3)/N(F)$。旧实现的 $R\Rightarrow F$ 在六个 v5 样本中均不成立；$J/\psi$ 的 $D\Rightarrow I$ 也均不成立。因此旧乘积相对直接累计效率偏低：$\phi$ 为 **3.34–9.74%**，leading $J/\psi$ 为 **10.87–14.66%**，subleading $J/\psi$ 为 **22.53–29.17%**。按实际地图 bin 核算，最大 populated fine-bin 偏差为 $\phi$ **10.16%**、stacked $J/\psi$ **40.08%**。[完整审计与逐样本表](/tmp/jjp_cumulative_efficiency_audit_20261022/REPORT.md)。

提交 `e63a938` 修正了 stacked map/cutflow 的 pairwise 分母；`f9e6c4e` 将对象链改为累计 mask，并增加对应测试。下文新的 closure 使用 `f9e6c4e`；上述偏差描述的是 `ed602ad` 时的实现及其地图语义，不能直接当成新 closure 的偏差来源。新源码不自动重写此前已保存的地图，使用旧产品时应按其生成版本辨认。

历史角分布诊断还发现另一个定义差别：legacy `kaonRECO` 从完整 composite 的 $\phi$ leg 匹配计算，测得的是“匹配 $\phi$ 出现在完整候选中”的概率。当前 singles 路径使用 muon、`RecoKaonTrack`、`SingleJpsi` 和 `SinglePhi`，TPS-Onia2MuMu 可以在没有完整 composite 时保存 MC singles。旧 parquet 中“无 composite 时 RECO flag 为零”不能推断原始 singles 为空，也不能把旧 $\phi$ `kaonRECO` 差异直接归因于两条 kaon 的径迹重建。[物理检查汇总](../.claude/worktrees/sps-cs-angular/diagnostics/sps_cs_angular_20261019/PHYSICS_CHECKS_SUMMARY_20261022.md)。

## 二、closure：历史与本次文件隔离结果

历史 MC Production v3 的 factorized self-closure corrected/GEN 在五个样本中为 **99.4–403.5**，显示当时严重失闭；它没有文件隔离，也没有保存误差。同期 correlated 5D 的高统计 self-closure 为 DPS1 **0.993**、DPS2_CS **0.990**、SPS_CS **0.985**，但跨 subprocess 转移可达 DPS1 map $\to$ SPS_CS **0.530**、反向 **1.761**。历史 acceptance 因子化是分 bin 诊断，不是完整事件 closure；未发现可量化的历史 hybrid/file-disjoint 结果。[历史溯源与数值](/tmp/jjp_closure_reassess_20261022_mxAG8k/REPORT.md)。

本次在 August v5 效率产品上按源文件确定性分成约 80% train、20% holdout。地图只由 train 文件重建；factorized 与 hybrid 在相同 holdout 上评估。区间来自 holdout 源文件的 10,000 次簇 bootstrap，训练地图固定。

| 样本 | 方法 | holdout GEN / selected | corrected/GEN（95% 文件簇区间） | lookup 失败 |
|---|---|---:|---:|---:|
| DPS1 | factorized | 79,713 / 1,771 | 0.9855 [0.9215, 1.0491] | 0 |
| DPS1 | hybrid | 79,713 / 1,771 | 0.9836 [0.9126, 1.0556] | 0 |
| SPS_CS | factorized | 155,578 / 1,230 | 0.8416 [0.7707, 0.9122] | 0 |
| SPS_CS | hybrid | 155,578 / 1,230 | 0.9420 [0.8323, 1.0555] | 0 |

DPS1 两种方法均与 1 相容；SPS_CS 的 factorized 偏低约 15.8%，hybrid 偏低约 5.8%。该结论针对 `Pri_assocPVPass` 所要求的同一 triple-GEN-matched composite 候选：通过 `s_cand`、触发与 muon matching、DiOnia vertex 和 associated-PV。best-score 候选只作诊断，不是 closure 的选中条件。区间未计入训练地图的统计波动。

在相同 holdout 上，`scand_factorization` 的 joint quality / `s_cand` 阶段 direct/product 为 DPS1 **1.108 [1.061, 1.154]**、SPS_CS **1.152 [1.095, 1.209]**。早期 fiducial、RECO、ID 的总体比值在约 0.985–1.028；quality 级的对象乘积低估联合通过率。逐 bin 离散更大，详见 [DPS1 逐 bin CSV](/tmp/jjp_closure_reassess_20261022_mxAG8k/scand_factorization_holdout/JJP_DPS1/scand_factorization_stage_bins.csv) 与 [SPS_CS 逐 bin CSV](/tmp/jjp_closure_reassess_20261022_mxAG8k/scand_factorization_holdout/JJP_SPS_CS/scand_factorization_stage_bins.csv)。

## 三、角变量、重算与物理解释

旧极角脚本把处于不同静止系的三动量直接点乘。修正后的 helicity 角把子粒子 $d$ 和母系统 $S$ 都变换到共振 $V$ 的静止系：

$$
\cos\theta_H=-\frac{\mathbf p_d^{\,(V)}\cdot\mathbf p_S^{\,(V)}}
{|\mathbf p_d^{\,(V)}|\,|\mathbf p_S^{\,(V)}|}.
$$

$J/\psi$ 使用正电荷 muon；$\phi$ 使用 leading-$p_T$ kaon 并报告 $|\cos\theta_\phi|$。两个 $J/\psi$ 的衰变平面夹角在共同 $JJ$ 静止系计算，定义自洽。合成事件整体非共线 boost 检查的最大残差为 $2.22\times10^{-16}$。已重算数据与五个 selected MC 的 reco、selected-GEN 角度；数据的 54 个质量 bin 拟合均为 `status=0, covQual=3`，四组分箱信号产额和相对全局拟合的差异均低于 0.6%。

| 样本 | selected 事件数 | $\langle c_{J/\psi_1}^2\rangle$ | $\langle c_{J/\psi_2}^2\rangle$ | $\langle c_\phi^2\rangle$ |
|---|---:|---:|---:|---:|
| DPS1 | 68,893 | 0.171515 | 0.134370 | 0.260991 |
| DPS2_CS | 32,533 | 0.113121 | 0.061492 | 0.234893 |
| DPS2_G | 966 | 0.176943 | 0.181767 | 0.240096 |
| SPS_CS | 7,977 | 0.128853 | 0.073580 | 0.234484 |
| SPS_G | 748 | 0.238800 | 0.315934 | 0.282368 |

数据扣本底后的 $\phi$ 二阶矩为 **$0.25469\pm0.02343$**，与 DPS1 和 SPS_CS 的上述 selected MC 值均相容。$J/\psi$ 的一些 selected moments 与 SPS_CS 仍有约 $3$–$4\sigma$ 的统计张力，尚未经效率修正。[当前角分布详细报告](../.claude/worktrees/sps-cs-angular/diagnostics/sps_cs_angular_20261019/outputs_helicity_corrected_20261019/REPORT_helicity_corrected_20261019.md)。

对 $c=|\cos\theta_\phi|$，把 SPS_CS 的 $(p_{T,\phi},|y_\phi|)$ 组成重加权到 DPS1（$10\times5$ 个 bin）后，$\langle c^2\rangle$ 从 **$0.234484\pm0.002906$** 到 **$0.256807\pm0.003687$**；DPS1 为 **$0.260991\pm0.001041$**。反向将 DPS1 重加权到 SPS_CS，得到 **$0.235235\pm0.001043$**，对应 SPS_CS 原值 **$0.234484\pm0.002906$**。这表明 selected 样本的总体二阶矩差异与 $\phi$ 运动学组成强相关。$\phi$ 的运动学改变两个 kaon 的实验室 $p_T,\eta$ 和被选择概率；重加权是在 selected 样本内检验组成效应。约 $1.1\sigma$ 的显著性使用统计误差近似，尚未传播权重估计和共同支撑区域的不确定度。

同一个 $M_2=(5\langle c^2\rangle-1)/2$ 可以作为两类衰变的角矩指标；若要解释为纵向自旋比例，在积分方位角且忽略轻子质量的理想分布中，$\rho_{00}^{(\phi\to KK)}=M_2$，$\rho_{00}^{(J/\psi\to\mu\mu)}=1-2M_2$。本文的数值是 **selected moment**，未作完整接受度与效率修正；selected-GEN 也来自已入选事件，不能代表 inclusive GEN 极化。v3 快度偏置按既有已知问题记录，后续生产批次已修复。

## 四、φ 来源与 beamspot 参考 ctau

这项补充调查以旧版 selected MC 的重建候选核对 $\phi$ 来源，以数据中的 $\phi$ ctau 分箱质量拟合检查正向尾部。所用横向投影量为

$$
\ell_{xy}=\frac{m_\phi}{p_{T,\phi}^{,2}}\,
\mathbf p_{T,\phi}\cdot(\mathbf v_\phi-\mathbf v_{\rm beamspot}).
$$

`Phi_ctau` 存储单位为 cm，图中换算为 mm。当前 selected ntuple 没有同时构造相对拟合 JJP 联合顶点位移所需的拟合 $\phi$ 与联合顶点横向坐标；`Pri_ctau` 或 selected PV 坐标不能替代该联合顶点。这里研究的是 $\phi$ 的**产生来源和重建位移**，不是测量 $\phi$ 共振的本征寿命。

### 五个旧版 selected MC：严格 GEN 系统匹配与祖先证据

五个旧版 selected MC 共 111,117 行。最终 best candidate 同时匹配效率 workflow 选定的两个不同 $J/\psi$ 母粒子及 $\phi$ 母粒子的严格代理样本共有 **108,925** 行。匹配时要求对应的直接 $\mu^+\mu^-$、$K^+K^-$ 子粒子及母粒子运动学资格；它比只核对 $\phi$ 的旧代理更严格。保留记录中的开放重味祖先证据如下：

| 旧版 selected MC | 严格匹配候选 | beauty 证据 | charm 证据 | 祖先不明 |
|---|---:|---:|---:|---:|
| DPS1 | 67,686 | 3 | 250 | 67,433 |
| DPS2_CS | 31,917 | 21 | 1,440 | 30,456 |
| DPS2_G | 948 | 0 | 51 | 897 |
| SPS_CS | 7,637 | 13 | 577 | 7,047 |
| SPS_G | 737 | 1 | 21 | 715 |
| **合计** | **108,925** | **38** | **2,339** | **106,548** |

`beauty` 表示保留的开放 beauty 强子祖先证据；`charm` 表示开放 charm 证据、但更上游 beauty 状态未解决。`祖先不明` 不是 prompt 类别。严格匹配后重味证据仍存在，说明它不全由选错 workflow $\phi$ 目标造成；这些数目只描述保留祖先记录，不能换算成物理 prompt/nonprompt 组成。[祖先证据 ctau 形状图](../diagnostics/phi_ctau_20261022/generator/reco_plots/origin_evidence_ctau_shapes.png)按证据类别展示五样本的重建 ctau；完整匹配迁移、祖先链与分类规则见[原调查报告](../diagnostics/phi_ctau_20261022/phi_ctau_subprocess_comparison.md)。

### 数据 ctau 分箱质量拟合

数据有 **48,829** 个 selected 事件，全部有有限且非 sentinel 的 $\phi$ ctau。独立的 3D 质量模型在每个 ctau bin 中拟合，中心设置的整体信号产额为 **$1560.2\pm142.8$**；$\phi$ ctau $\geq0.1\,\mathrm{cm}$ 的正向尾部为 **$79.1\pm31.6$**。该尾部包含 1,880 条原始 selected 数据行，原始行数含背景，不是信号产额。

| 模型设置 | $\sigma_\phi$ 允许上限 | 正向尾部信号产额 |
|---|---:|---:|
| 中心设置 | 0.005 GeV | $79.05\pm31.56$ |
| 放宽质量分辨率上限 | 0.010 GeV | $190.63\pm44.87$ |

$\sigma_\phi$ 是高斯**探测器质量分辨率**参数；两种设置中共振本征宽度 $\Gamma_\phi=0.004249\,\mathrm{GeV}$ 均固定。尾部产额随 $\sigma_\phi$ 上限显著变化，因此当前质量模型无法给出稳定的数据 nonprompt 成分。[正向尾部模型敏感性图](../diagnostics/phi_ctau_20261022/generator/reco_plots/tail_model_sensitivity.png)直接展示该变化。这里的 ctau 分箱拟合与第三节的角度分箱拟合是同一 selected 数据的两套独立拟合，不将两者的产额相加。

### 六个较新 GEN 产品的运动学比较

较新效率流程的六个 `gen_systems.parquet` 共含 **3,588,650** 个通过母系统条件的 workflow-target 行，其中记录 $\phi$ 的 $p_T$ 与 $y$，但没有用于本次来源分类的祖先链或 ctau。各样本的 GEN-B 全系统 fiducial 代理比例约为 **4.34%–9.29%**；这些是产品内的逐行比例，不是过程截面或旧版重建候选的产额比例。主要快度比较使用[六样本 $|y(\phi)|$ 对照图](../diagnostics/phi_ctau_20261022/generator/phi_abs_y_counts_and_shapes.png)，以避开已知的带符号快度不对称。五个旧版 selected MC 的祖先与 ctau 分布和六个较新 GEN workflow-target 运动学产品分属不同批次，不能合并成来源或产额比例；其样本对应关系与数值表见[原调查报告](../diagnostics/phi_ctau_20261022/phi_ctau_subprocess_comparison.md)。

## 图表与复现命令

### 2026-10-22 累计链修复后的新版效率图

已用当前提交 `f9e6c4e` 从六样本 all6 merged `gen_systems.parquet` 与 `event_step_flags.parquet` 在全新目录[efficiency_maps_cumulative_20261022](../efficiency_maps_cumulative_20261022/)重建基础效率地图、11 个 factorized correction maps、post-acceptance 5D 地图及派生效率图。每个样本有 12 个 correction map parquet 和 230 张 PNG，共 **72 个 correction map 文件、1,380 张 PNG**；六个样本均有派生 manifest。来源目录为 `/home/storage29/users/chiwang/JpsiJpsiPhi/analysis/Efficiency/20260831_jjp_efficiency_new_samples/downstream_all6_20260901_01/merged`，旧产品未覆盖。[运行日志](../efficiency_maps_cumulative_20261022/run.log)。

新版图按样本位于 `efficiency_maps_cumulative_20261022/derived/<sample>/derived/plots/`，含 `cumulative/`、`acceptance/`、`conditional/`、`pair_vertex/` 与 `stacked_jpsi/`。可先看[DPS1 $J/\psi$ leading dimuon 累计效率](../efficiency_maps_cumulative_20261022/derived/JJP_DPS1/derived/plots/cumulative/cumulative_object2d_jpsi_lead_dimuon.png)、[SPS_CS 同一图](../efficiency_maps_cumulative_20261022/derived/JJP_SPS_CS/derived/plots/cumulative/cumulative_object2d_jpsi_lead_dimuon.png)，以及[DPS1 stacked $J/\psi$ dimuon 图](../efficiency_maps_cumulative_20261022/derived/JJP_DPS1/derived/plots/stacked_jpsi/stacked_jpsi_absy_dimuon.png)。这些是修复后的效率图；历史 `downstream_efficiency_plots_20260901_01` 图属于旧地图版本。

### 统一验证图集（2026-10-22）

上段 1,380 张图记录的是此前完整重绘，包含累计图和带不确定度的 QA 图。当前软件的**默认图集**从同一批六样本 merged/derived parquet 绘制 acceptance、conditional、pair-level、stacked-J/ψ 图，不画累计图，也不在效率热图上显示不确定度。累计计数及 parquet 地图仍用于效率修正。若需要旧图，可显式加 `--with-cumulative-plots` 或 `--with-uncertainty-plots`。

在包含本次改动的独立 worktree（或合并后的仓库）中，统一入口 `scripts/efficiency/plot_validation.py --plots` 可选择 `stepwise`、`closure`、`factorization`、`angular`、`phi-origin`、`phi-ctau`、`phi-gen` 或 `all`；也接受逗号分隔的多个名字。GNU Make 按目标管理依赖：已有中间文件直接复用，缺失时补做所需 ROOT 提取或 RooFit。默认 closure 图对比 DPS1 与 SPS_CS 的 factorized/hybrid 文件隔离结果。`phi-origin` 的计数与形状基于五个旧版 selected MC 的完整 GEN 系统严格匹配；`phi-gen` 的 $|y(\phi)|$ 基于六个较新 workflow-target GEN 样本，不将两批样本相除。

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh
python3 scripts/efficiency/plot_validation.py \
  --plots all --output-dir validation_plots_20261022
# 按需只重画默认六样本效率图：--plots stepwise
# 显式旧图：--plots stepwise --with-cumulative-plots --with-uncertainty-plots
```

图集入口文件为 `validation_manifest.json`；`stepwise/default/` 保存六样本图和 derived manifest，`closure/` 与 `factorization/` 保存输入数表及对照图，`angular/` 保存角分布与 $\phi$ 重加权图，`phi/` 保存祖先证据、尾部模型敏感性及六样本 $|y(\phi)|$ 图。用于 slides 时，closure 图展示两种修正方法的 holdout 比值；φ 来源图展示证据分类后的 ctau 形状；尾部图展示同一数据在两个质量分辨率范围下的拟合变化。各图旁的 JSON 保存绘图所用数值和群体标签。

从同一 merged 输入再次生成时，依次运行 `scripts/efficiency/rebuild_efficiency_maps.py` 到全新目录、`python3 -m efficiency_workflow.build_factorized_maps`、同一命令加 `--build-post-acceptance`、最后 `scripts/efficiency/build_derived_efficiency.py --plot-scope both`。`--build-post-acceptance` 只生成条件 5D 地图，不同时生成 11 个 factorized 地图。所有 Python 命令需先加载 LCG 109a，且输出目录保持独立以免覆盖已有产品。

现成图表：[重新排版的 $\phi$ 重加权图](../.claude/worktrees/sps-cs-angular/diagnostics/sps_cs_angular_20261019/outputs_helicity_corrected_20261019/comparison/phi_reweighting_layout_20261022/phi_polarization_reweighting.png)、[修正前后 $\phi$ 角矩图](../.claude/worktrees/sps-cs-angular/diagnostics/sps_cs_angular_20261019/outputs_helicity_corrected_20261019/helicity_moment_comparison/old_new_abs_cos_theta_phi.png)、[数据与 MC 扣本底角图](../.claude/worktrees/sps-cs-angular/diagnostics/sps_cs_angular_20261019/outputs_helicity_corrected_20261019/plots/subtracted_abs_cos_theta_phi.png)。closure 与分母审计的本次产物以表格/CSV 保存；上面的数值表可直接用于作图。

$\phi$ 来源/ctau 的三张关键图分别是[祖先证据 ctau 形状](../diagnostics/phi_ctau_20261022/generator/reco_plots/origin_evidence_ctau_shapes.png)、[正向尾部模型敏感性](../diagnostics/phi_ctau_20261022/generator/reco_plots/tail_model_sensitivity.png)和[六样本 $|y(\phi)|$ 对照](../diagnostics/phi_ctau_20261022/generator/phi_abs_y_counts_and_shapes.png)。前两张基于五个旧版 selected MC 或 selected 数据，第三张基于六个较新 GEN workflow-target 产品；各图的输入、定义与生成记录见[原调查报告](../diagnostics/phi_ctau_20261022/phi_ctau_subprocess_comparison.md)。

以下命令从仓库根目录运行，仅根据已保存的角表和质量拟合结果重新绘图，写入新的 `/tmp/chiw` 目录：

```bash
cd /home/storage29/users/chiwang/JpsiJpsiPhi/analysis/Efficiency/NtupleAnalyzer
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh
D="$PWD/.claude/worktrees/sps-cs-angular/diagnostics/sps_cs_angular_20261019"
O="$D/outputs_helicity_corrected_20261019"
P=/tmp/chiw/jjp_result_plots_20261022
mkdir -p "$P"

python3 "$D/scripts/plot_angles.py" \
  --angles-dir "$O/angles" --binned-dir "$O/binned_angles" \
  --output-dir "$P/angular"
python3 "$D/scripts/check_phi_polarization.py" \
  --angles-dir "$O/angles" --output-dir "$P/phi_reweighting"
python3 "$D/scripts/compare_helicity_moments.py" \
  --old-dir "$D/outputs" --new-dir "$O" \
  --output-dir "$P/old_new_angles"
```

完整角分析的 ROOT 输入、质量拟合与脚本参数见[诊断目录 README](../.claude/worktrees/sps-cs-angular/diagnostics/sps_cs_angular_20261019/README.md)。如需重新运行文件隔离 closure，而不是仅绘图，可按[closure 报告](/tmp/jjp_closure_reassess_20261022_mxAG8k/REPORT.md)中的 split 和输入版本使用 `python3 -m efficiency_workflow.closure`，并写入新目录。

## 下载

在另一台已配置 SSH 别名 `hepthu-el9` 的机器上，**先进入目标下载目录**，然后运行下列命令。每条命令都下载到当前目录 `./`；目录型产物保留其目录名。

```bash
repo=hepthu-el9:/home/storage29/users/chiwang/JpsiJpsiPhi/analysis/Efficiency/NtupleAnalyzer
angular="$repo/.claude/worktrees/sps-cs-angular/diagnostics/sps_cs_angular_20261019/outputs_helicity_corrected_20261019"
phi="$repo/diagnostics/phi_ctau_20261022"

rsync -avPm "$repo/validation_plots_20261022/JJP_Efficiency_Angular_Results_20261022.md" ./
rsync -avPm "$angular/plots" ./
rsync -avPm "$angular/comparison/phi_reweighting_layout_20261022" ./
rsync -avPm "$angular/helicity_moment_comparison/old_new_abs_cos_theta_phi.png" ./
rsync -avPm "$repo/efficiency_maps_cumulative_20261022/derived" ./
rsync -avPm "$repo/validation_plots_20261022" ./
rsync -avPm "$phi/phi_ctau_subprocess_comparison.md" ./
rsync -avPm "$phi/generator/reco_plots/origin_evidence_ctau_shapes.png" ./
rsync -avPm "$phi/generator/reco_plots/tail_model_sensitivity.png" ./
rsync -avPm "$phi/generator/phi_abs_y_counts_and_shapes.png" ./
```

若需完整分析脚本与所有历史/修正后图表，可下载整个[角诊断目录](../.claude/worktrees/sps-cs-angular/diagnostics/sps_cs_angular_20261019/README.md)。审计原始结果分别在[累计分母报告](/tmp/jjp_cumulative_efficiency_audit_20261022/REPORT.md)、[closure 报告](/tmp/jjp_closure_reassess_20261022_mxAG8k/REPORT.md)及[closure 汇总 CSV](/tmp/jjp_closure_reassess_20261022_mxAG8k/closure_reassessment_summary.csv)。

## 新会话制作简明 slides 的交接说明

将本 Markdown 和当前目录中下载的图交给新会话即可。建议用五页呈现：①问题与版本时间线；②旧对象链分母问题、修正及新版效率图；③ DPS1/SPS_CS 的 file-disjoint closure 对照；④角度修正与 $\phi$ 重加权；⑤ $\phi$ 来源证据及数据 ctau 尾部模型敏感性。第③页的四个 closure 点直接取本文表格；第②页用本文的旧乘积偏差范围，无须把旧审计数值画成新地图结果。

| 下载文件 | 放进 slides 的作用 | 读图要点 |
|---|---|---|
| `JJP_Efficiency_Angular_Results_20261022.md` | 文字和数值主来源 | 保持 `ed602ad` 旧审计与 `f9e6c4e` 新 closure 的版本顺序。 |
| `old_new_abs_cos_theta_phi.png` | 展示极角定义修正的影响 | 新旧角矩不同，后续定量比较统一采用修正后的角。 |
| `phi_reweighting_layout_20261022/phi_polarization_reweighting.png` | 展示 SPS_CS→DPS1 二维运动学重加权 | selected $\phi$ 二阶矩差异从约 $8.6\sigma$ 缩至约 $1.1\sigma$。 |
| `plots/subtracted_abs_cos_theta_phi.png` | 展示数据与 MC 的修正角分布 | 数据已按角度 bin 的质量拟合扣本底；形状是 selected 级别。 |
| `plots/moments_summary.png` | 展示多个角变量的结果概览 | 可以作为备用页，主线优先放 $\phi$ 与 closure。 |
| `derived/<sample>/derived/plots/` | 展示累计链修复后的新版效率地图 | 可选 DPS1 与 SPS_CS 同一对象/步骤的图并排；图来自当前代码重新计算的地图。 |
| `origin_evidence_ctau_shapes.png` | 展示五个旧版 MC 中可识别祖先证据的 ctau 形状 | 38 个 beauty 与 2,339 个 charm 证据来自 108,925 个严格匹配候选；其余来源不明。 |
| `tail_model_sensitivity.png` | 展示数据正向 ctau 尾部的质量模型敏感性 | 放宽探测器质量分辨率 $\sigma_\phi$ 上限，尾部拟合产额从约 79 变为约 191；$\Gamma_\phi$ 固定。 |
| `phi_abs_y_counts_and_shapes.png` | 展示六个较新 GEN workflow-target 产品的 $|y(\phi)|$ 差别 | 这是运动学对照；与五个旧版 selected MC 的祖先计数分开解释。 |
| `phi_ctau_subprocess_comparison.md` | 保存来源匹配、ctau 拟合与图表的完整定义 | 查阅严格系统匹配规则、逐样本证据计数和模型设置。 |

给新会话的核心背景：历史 v3 效率定义混入 composite 门控；v5 对象链分母在旧提交中未累计，当前源码已修；重新构图的 holdout closure 表明 DPS1 两种修正均接近 1，SPS_CS 的 hybrid 比 factorized 更接近 1；独立的对象间质量级乘积仍低估联合通过率。角度脚本修正了跨参考系点乘后，$\phi$ selected 二阶矩的样本差异与 $(p_T,|y|)$ 组成高度相关。严格匹配的五个旧版 MC 保留开放重味祖先证据；数据正向 ctau 尾部拟合对探测器质量分辨率范围敏感。slides 中将“selected 角矩”作为观测结果呈现，将重味祖先计数作为保留证据计数呈现；物理极化和数据 prompt/nonprompt 比例分别需要进一步的效率处理与稳定的 ctau 信号模型。
