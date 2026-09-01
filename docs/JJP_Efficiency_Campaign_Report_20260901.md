# JJP 效率 campaign 报告，2026-09-01

## 执行摘要

本轮 JJP 效率 campaign 已完成六个 MC 样本的合并产品交接、统一布局、派生效率产品、factorized correction maps、效率图和一次 factorized 数据校正链。六个规范样本名为 `JJP_DPS1`、`JJP_DPS2_CS`、`JJP_DPS2_G`、`JJP_SPS_CS`、`JJP_SPS_G` 与 `JJP_TPS`。`JJP_TPS_MC_v4_1` 只保留在外部存储路径和历史 provenance 中，不再作为分析样本键。

正式 factorized yield JSON 以 `JJP_DPS1` 为 nominal：未校正信号产额为 1560.19 +/- 142.82，校正后为 96295.46 +/- 16045.61（统计）。代码同时给出六样本包络半宽 66962.62 和总不确定度 78509.25；这两个数是当前 subprocess 比较的程序输出，尚不是完整的物理系统学评估。

已完成的产物位于 storage29。原始 CCEOS 读取和逐文件预处理留在 IHEP scratchfs2，随后只交接经校验的紧凑 tarball 到 CERN EOS，并从 EOS 送往 `hepthu-el9` 的 storage29。此次流程没有使用 publicfs。

## 范围、样本和处理记录

| 样本 | 文件数 | source entries | retained candidate events | 本轮最终分析键 |
| --- | ---: | ---: | ---: | --- |
| `JJP_DPS1` | 888 | 3,812,832 | 221,766 | `JJP_DPS1` |
| `JJP_DPS2_CS` | 4,840 | 24,197,163 | 698,494 | `JJP_DPS2_CS` |
| `JJP_DPS2_G` | 730 | 291,458 | 13,543 | `JJP_DPS2_G` |
| `JJP_SPS_CS` | 4,840 | 17,615,553 | 436,669 | `JJP_SPS_CS` |
| `JJP_SPS_G` | 292 | 230,914 | 10,147 | `JJP_SPS_G` |
| `JJP_TPS` | 317 | 1,472,109 | 93,904 | `JJP_TPS` |

v5 workspace `/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/20260830T094618Z_jjp_efficiency_v5` 产生前五个样本的合并产品。v6 workspace `/scratchfs2/cms/wangchi/hepjobs/NtupleAnalyzer/20260831T080800Z_jjp_efficiency_v6_tps_rebind` 对 TPS 做了 metadata-only rebind：将下游分析身份从生产目录名 `JJP_TPS_MC_v4_1` 绑定为 `JJP_TPS`，并保留相同的 317 个文件、1,472,109 个 entries 和 93,904 个 retained candidate events。它不是一次新的原始 ntuple 处理。

## 已完成的架构和交接

IHEP 的 scratchfs2 执行 CCEOS 就近预处理和形式化合并。每个样本随后被打为一个紧凑 tarball，tarball 的整体 SHA-256 和成员大小写入 sidecar。六个 tarball 及六个 sidecar 被 stage 到：

```text
/eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV/handoff/20260831_jjp_efficiency_new_samples/bundles
```

`eos_staging_report.json` 记录 12 个 staged 文件，文件名集合、大小和六个 tarball 的 SHA-256 均匹配。storage29 的接收根目录为：

```text
/home/storage29/users/chiwang/JpsiJpsiPhi/analysis/Efficiency/20260831_jjp_efficiency_new_samples
```

`handoff_provenance.json` 保存 v5、v6 来源路径、每个 bundle 的整体 SHA-256、大小和 formal manifest ID。解包后的转移验证确认每个样本的 formal manifest identity、文件覆盖和核心 Parquet 结构。最初的逐行检查把 `event_step_flags` 误与 retained events 比较；`transfer_validation_rowcount_addendum.json` 更正了检查对象：它应与 `gen_systems` 行数相等。六个样本均通过该更正后的行数检查。

下游先建立五样本 factorized 视图，再建立 TPS 视图，最后形成统一六样本布局：

```text
downstream_all6_20260901_01/
  merged/<sample>/
  derived/<sample>/derived/
```

统一视图验证通过：六个样本键正确，120 个派生输出、66 个 factorized map 和 36 个核心 Parquet 可由 LCG 109a 读取。TPS 的 formal manifest ID 为 `3389ae8ca6733d82f34e23d88d4fcfcf0c2a0253f47dcb1ad21547d85c437e7a`。五样本 factorized 验证报告显示每样本 11 个 factor，且 56 个输入文件通过 hardlink 供下游使用。

## 已完成的软件修正和测试

- factorized maps 构建器补齐了效率定义和 JSON 读取的相对导入，测试 fixture 也提供了必要的 `configuration_metadata.json`。
- TPS 新的 canonical 名称是 `JJP_TPS`。manifest 生成器、处理 runbook 和契约测试已同步；历史生产名仍可出现在原始 URL 中。
- SSH 端点固定为 `hepthu-el9`，连接后必须确认 `hostname -s` 为 `nd-29` 且 `/home/storage29` 存在，避免通用 `hepthu` alias 落到错误主机。
- RooPlot 图例查询由不存在的 `input_filedObject` 改为 `findObject`。回归测试 `test_projection_plot_resolves_named_rooplot_objects` 覆盖了 PDF 和 PNG 投影图的生成。
- 本轮包含 formal merge、TPS manifest、TPS processing contract、factorized maps、fit sPlot schema 等定向测试。报告只把上述通过的验证作为完成证据，不把未运行的完整物理验证写成已完成。

## Factorized 数据结果

正式运行读取 `jjp_data_selected.root` 的 `selected` tree，对 48,829 个 selected events 做六个样本的 factorized lookup。每个样本的 missing 和 invalid 均为零。`n_interpolated` 是 fine、coarse 或 inclusive fallback 的组件计数，可能大于事件数。

| map sample | 校正产额 | fit 统计误差 | MC 统计不确定度 | mean weight |
| --- | ---: | ---: | ---: | ---: |
| `JJP_DPS1` | 96,295.46 | 16,045.61 | 37,712.70 | 61.24 |
| `JJP_DPS2_CS` | 122,700.88 | 21,506.16 | 20,360.24 | 79.53 |
| `JJP_DPS2_G` | 110,370.86 | 18,467.01 | 140,153.15 | 71.92 |
| `JJP_SPS_CS` | 211,004.93 | 37,027.74 | 98,408.02 | 138.97 |
| `JJP_SPS_G` | 113,094.05 | 19,435.81 | 213,913.40 | 73.59 |
| `JJP_TPS` | 77,079.68 | 12,029.23 | 31,719.89 | 47.97 |

Nominal 的完整 corrected ROOT 为 `formal_factorized/jjp_data_factorized_corrected_nominal.root`，写入 48,829 entries。其后 sPlot 使用 `--effcorr-weight-branch effcorr_weight`，而不是 fit weight。该 fit 的 signal yield 为 1560.47，background yield 为 47268.71，sss-only LRT significance 为 12.009。输出 ROOT 含 `signal_effcorr_sw`。`plot_weighted_distributions.py` 以该 branch 生成了 105 个校正信号 1D 分布。

这里的 105 是 `sel_*` 标量 branch 对应的 1D 图数量。校正分布目录另有 11 个
pair overlay 或 correlation 图，因此实际文件数是 116 个 PNG 和 116 个 PDF。

## 效率图

正式的 `scripts/efficiency/build_derived_efficiency.py` all-scope 运行生成 1,356 个 PNG，即每样本 226 个。每个样本有 113 张 nominal 图和 113 张不确定度图，类别为 52 张 cumulative、7 张 acceptance、49 张 conditional 和 5 张 pair-vertex 图。Pillow 成功解码全部 1,356 张图，没有零字节 PNG 或非 PNG 文件签名。

factorized maps 对全部六样本均存在，但当前仓库没有一个受支持的 factorized correction-map 可视化 CLI。因此本轮没有把未实现的可视化功能替换成非正式图。

## 已定位并修复的问题

| 问题 | 原因 | 处理结果 |
| --- | --- | --- |
| IHEP CCEOS 访问失败 | shard runner 清除了 `X509_USER_PROXY`，使作业找不到传入的 proxy | 按 `IHEP_X509_Proxy_Guidelines.md` 的优先级传递 scratchfs2 中的 proxy，不再 unset 该变量 |
| TPS manifest 身份混用 | 生产名 `JJP_TPS_MC_v4_1` 与分析键 `JJP_TPS` 同时出现 | v6 metadata-only rebind 保留 formal identity，并在 all6 layout 中只使用 `JJP_TPS` |
| 错误的 hepthu alias | 通用 `hepthu` 可落到 `nd-0`，不是 storage29 节点 | 固定 `hepthu-el9`，并加入 `nd-29` 和 `/home/storage29` 断言 |
| rsync 在 AFS 凭据过期后失败 | AFS token 失效使仓库和传输端访问失败 | 后续交接使用新会话中的有效凭据；长期守护方案见下文 |
| Matplotlib 失败或警告 | 无 DISPLAY，且 `/home/storage29/.config/matplotlib` 不可写 | 使用 `MPLBACKEND=Agg` 和每次运行独立、可写的 `MPLCONFIGDIR` |
| RooPlot 投影图图例失败 | 机械重命名产生了 `input_filedObject`，不是 RooPlot API | 改为 `findObject` 并加入回归测试 |
| 根目录派生脚本 wrapper | 当时部署的 root wrapper 没有调用目标模块的 `main()` | 正式运行显式使用 `scripts/efficiency/build_derived_efficiency.py` |

## 从已合并六样本 Parquet 复现最终效率分析

以下命令从已完成的 merged 和 factorized products 开始，不包含 IHEP 原始 ntuple 预处理，也不覆盖现有产物。统一 all6 输入的实际层级是 `merged/<sample>`，而 `build_derived_efficiency.py` 需要 flat 的 `<input-dir>/<sample>`。factorized yield 只需要 `<efficiency-dir>/<sample>/maps`，因此下面创建新的 hardlink adapter 和独立的 `efficiency_view`。

先从 CERN 登录到固定的 storage29 节点：

```bash
ssh -F /afs/cern.ch/user/c/chiw/.ssh/config hepthu-el9
test "$(hostname -s)" = nd-29
test -d /home/storage29
```

进入部署的分析仓库。后面的 `python3` 命令都从这个目录执行：

```bash
cd /home/storage29/users/chiwang/JpsiJpsiPhi/analysis/Efficiency/NtupleAnalyzer
```

在同一个 shell 中建立本次复现的全新目录、LCG 环境和无显示绘图环境。`RUN_TAG` 必须是新的值。

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_109a/x86_64-el9-gcc13-opt/setup.sh
export RUN_TAG="repro_$(date -u +%Y%m%dT%H%M%SZ)"
export BASE=/home/storage29/users/chiwang/JpsiJpsiPhi/analysis/Efficiency/20260831_jjp_efficiency_new_samples
export SOURCE="$BASE/downstream_all6_20260901_01"
export REPRO="$BASE/$RUN_TAG"
test ! -e "$REPRO" || { echo "refusing to overwrite $REPRO"; exit 1; }
mkdir "$REPRO" "$REPRO/adapter" "$REPRO/efficiency_view"
export MPLBACKEND=Agg
export MPLCONFIGDIR="$REPRO/mplconfig"
mkdir "$MPLCONFIGDIR"
```

建立 adapter。这里的 `ln` 是 hard link，不会改写 source；新目录必须仍与 source 位于同一 storage29 filesystem。`adapter` 供派生效率脚本读取核心 Parquet，`efficiency_view` 供 factorized yield 读取 11 个 maps。

```bash
for sample in JJP_DPS1 JJP_DPS2_CS JJP_DPS2_G JJP_SPS_CS JJP_SPS_G JJP_TPS; do
  mkdir "$REPRO/adapter/$sample" "$REPRO/efficiency_view/$sample" "$REPRO/efficiency_view/$sample/maps"
  find "$SOURCE/merged/$sample" -maxdepth 1 -type f -exec ln {} "$REPRO/adapter/$sample/" \;
  if test -d "$SOURCE/merged/$sample/maps"; then
    find "$SOURCE/merged/$sample/maps" -maxdepth 1 -type f -name '*.parquet' -exec ln {} "$REPRO/efficiency_view/$sample/maps/" \;
  fi
done
ln "$SOURCE/merged/manifest.json" "$REPRO/adapter/manifest.json"
```

现有 all6 source 已有 66 个 factorized maps，故不应默认 rebuild。只有当新的 merged 输入确实没有 `maps/` 时，才在新 adapter 上执行下列命令；它会在 adapter 内创建 maps：

```bash
python3 -m efficiency_workflow.build_factorized_maps \
  --input-dir "$REPRO/adapter" \
  --samples JJP_DPS1 JJP_DPS2_CS JJP_DPS2_G JJP_SPS_CS JJP_SPS_G JJP_TPS
```

若上一步确实重建了 maps，把新 maps 链接到 yield 视图：

```bash
for sample in JJP_DPS1 JJP_DPS2_CS JJP_DPS2_G JJP_SPS_CS JJP_SPS_G JJP_TPS; do
  find "$REPRO/adapter/$sample/maps" -maxdepth 1 -type f -name '*.parquet' -exec ln {} "$REPRO/efficiency_view/$sample/maps/" \;
done
```

正式派生效率和 all-scope 图使用脚本目录中的入口，不使用根目录 wrapper：

```bash
python3 scripts/efficiency/build_derived_efficiency.py \
  --input-dir "$REPRO/adapter" \
  --output-dir "$REPRO/derived" \
  --plot-scope all \
  --min-plot-total 1
```

随后运行六样本 factorized yield，显式列出 `JJP_TPS`，并写出 nominal corrected ROOT：

```bash
python3 scripts/efficiency/compute_efficiency_corrected_yield.py \
  --data-input /home/storage29/users/chiwang/JpsiJpsiPhi/analysis/Efficiency/jjp_data_selected.root \
  --efficiency-dir "$REPRO/efficiency_view" \
  --samples JJP_DPS1 JJP_DPS2_CS JJP_DPS2_G JJP_SPS_CS JJP_SPS_G JJP_TPS \
  --nominal-sample JJP_DPS1 \
  --correction-mode factorized \
  --temp-dir "$REPRO/factorized/weighted_trees" \
  --plot-dir "$REPRO/factorized/yield_plots" \
  --corrected-root "$REPRO/factorized/jjp_data_factorized_corrected_nominal.root" \
  --corrected-root-sample JJP_DPS1 \
  -o "$REPRO/factorized/yield_factorized_all6.json" \
  -j 4
```

该 data ROOT 使用 `selected` tree。sPlot 只读取 `effcorr_weight` 来写 `signal_effcorr_sw`，不要添加 `--fit-weight-branch`：

```bash
python3 scripts/kinematics/fit_splot.py \
  --channel JJP --dataset data \
  -i "$REPRO/factorized/jjp_data_factorized_corrected_nominal.root" \
  -o "$REPRO/factorized/splot_corrected/jjp_data_factorized_sweighted.root" \
  --plot-dir "$REPRO/factorized/splot_corrected/fit_projection_plots" \
  --effcorr-weight-branch effcorr_weight \
  -j 4

python3 scripts/kinematics/plot_weighted_distributions.py \
  --channel JJP --dataset data \
  -i "$REPRO/factorized/splot_corrected/jjp_data_factorized_sweighted.root" \
  -o "$REPRO/factorized/corrected_signal_distributions" \
  --weight-branch signal_effcorr_sw
```

## 尚未完成的项目和恢复位置

- 未实现 factorized correction maps 的专用可视化器，因此没有这类图。现有 1,356 张图是 cumulative、acceptance、conditional 和 pair-vertex 图。
- 没有构建 hybrid mode 所需的 post-acceptance 5D maps，因此没有 hybrid corrected yield。
- 没有进行 file-disjoint closure、完整系统学研究或不同 nominal/subprocess 物理选择的审核。当前 JSON 的 envelope 不能替代这些工作。
- 没有改变数据选择、J/psi 排序、fallback 阈值或 nominal 样本。上述可复制命令保持本轮的 factorized 设置。

恢复时从 storage29 的 `downstream_all6_20260901_01` 开始。先按上一节创建新的 `RUN_TAG`，再决定只重跑派生图、重跑 factorized yield，还是先补做 closure、hybrid maps 或系统学。不要向已完成的 campaign 目录写入新输出。

凭据守护器的设计已写入 campaign skill，但本轮没有把它作为可执行程序部署。它应是 orchestrator 之外的 OS 级 detached 服务，固定每 4 小时一次，只检查并在可续期时执行非交互式 `kinit -R`、`aklog`、`klist`、`tokens` 和一次 AFS read。它只写 heartbeat/status 并提示暂停 remote writes，不能提交、重试、删除或修改分析作业，也不能提示输入密码。

## 权威路径和验证证据

| 用途 | 路径或记录 |
| --- | --- |
| storage29 campaign 根目录 | `/home/storage29/users/chiwang/JpsiJpsiPhi/analysis/Efficiency/20260831_jjp_efficiency_new_samples` |
| 统一六样本产品 | `downstream_all6_20260901_01` |
| 效率图和验证 | `downstream_efficiency_plots_20260901_01/plots_all6` 与 `validation_report.txt` |
| 正式 factorized JSON、ROOT、sPlot 和分布图 | `downstream_plots_20260901_01/formal_factorized` |
| handoff、EOS 和 transfer 证据 | `handoff_provenance.json`、`eos_staging_report.json`、`reports/transfer_validation_report.json`、`reports/transfer_validation_rowcount_addendum.json` |
| 本地 canonical TPS manifest | `configs/efficiency/manifests/JJP_TPS.manifest.json` |
| 本地处理契约 | `docs/TPS_Efficiency_Processing.md` |

完成状态以 storage29 的 `all6_view_validation.txt`、`factorized_validation.txt`、`validation_report.txt`、正式 `yield_factorized_all6.json` 和相关日志为准。本地工作树在撰写本报告时已有其他未提交改动；本报告未修改这些文件。
