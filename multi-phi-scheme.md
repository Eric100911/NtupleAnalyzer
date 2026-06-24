## 2026.5.27


### 多候选与多 $\phi$ 情况下效率修正问题的起因、分析与建议方案

#### 1. 问题起因

在 $J/\psi J/\psi \phi$ 分析中，一个事件内可能存在多个 reconstructed candidates。当前数据端通常采用 **single best candidate per event** 的策略，即对所有通过基本质量、顶点、粒子识别等要求的候选计算

$$
S(c)=\sqrt{
p_{T,J/\psi_1}^2+
p_{T,J/\psi_2}^2+
p_{T,\phi}^2
},
$$

并保留 (S) 最大的候选：

$$
c_{\rm reco}^{*}
=

\arg\max_{c\in \mathcal{C}_{\rm reco}} S(c).
$$

这样每个事件只向 invariant-mass distribution 或微分截面直方图贡献一个候选。

问题出现在 MC truth definition。当前效率 workflow 中，生成层面通常会选取两个 hardest $J/\phi$ 和一个 hardest $\phi$ 作为目标系统：

$$
c_{\rm gen}^{\rm hard}
=

J/\psi_{1,\rm hard}
+
J/\psi_{2,\rm hard}
+
\phi_{\rm hard}.
$$

但是实际 Ntuple 中可能存在多个 gen $\phi$。这些额外 $\phi$ 可能来自 parton shower 或其他软 QCD 活动，并不一定是我们希望研究的“硬散射”对象；但在重建层面，它们的 $K^+K^-$ 衰变产物可能进入 $\phi$ 质量窗，并与两个 $J/\phi$ 组合成合法 candidate。

因此会出现如下情况：

$$
c_{\rm gen}^{*}
=

J/\psi J/\psi \phi_a,
$$

但重建端 best-score candidate 是

$$
c_{\rm reco}^{*}
=

J/\psi J/\psi \phi_b,
\qquad
\phi_b\neq \phi_a.
$$

这就是 candidate mismatch。

类似的 $J/\phi$-pair 与 (J/\psi+\psi(2S)) 分析中，acceptance、efficiency、data correction 和 closure test 本来就是标准结构。例如 (J/\psi+\psi(2S)) AN 将 acceptance calculation、efficiency calculation、correction to dataset、closure test 连续作为效率修正章节内容 ；double-$J/\phi$ AN 也同样将 acceptance、efficiency、closure test、correction to dataset 作为一组核心步骤 。但本分析的特殊点在于：由于可能存在多个 $\phi$ 和多个 $K^+K^-$ 组合，**candidate choice 本身成为了效率修正的一部分**。

---

#### 2. 为什么 hardest-$\phi$ truth definition 不够稳健

如果效率分母只认 hardest gen $\phi$，那么效率定义实际对应的是：

$$
pp\to J/\psi J/\psi \phi_{\rm hard}+X.
$$

但数据端 best-score candidate 可能接受任意一个可重建、可通过选择的 $\phi$：

$$
pp\to J/\psi J/\psi \phi_{\rm selected}+X.
$$

这两个对象不一定相同。于是会出现逻辑不一致：

$$
\text{reco candidate matches softer } \phi
\Rightarrow
\text{passes analysis selection},
$$

但在 hardest-$\phi$-based efficiency workflow 中：

$$
\text{same candidate}
\Rightarrow
\text{fails truth matching}.
$$

这说明当前问题不是普通的效率损失，而是 **GEN 分母定义和 RECO 分子定义不一致**。

如果继续使用 hardest-$\phi$ 定义计算效率，而数据端又允许 softer $\phi$ 进入 best candidate，那么修正因子并不严格对应真实数据选择。尤其在含 $\phi$ 的微分变量中，例如

$$
p_T(\phi),\quad
y(\phi),\quad
m(J/\psi J/\psi\phi),\quad
p_T(J/\psi J/\psi\phi),
$$

选中不同的 $\phi$ 会直接改变事件落入的 bin。

---

#### 3. 为什么需要引入 candChoice 这一项

这里的 candChoice 不应理解为一个新的物理效率，而应理解为一个 **analysis response**，即分析算法从多个候选中选择最终候选所带来的响应效应。

可以定义：

$$
\epsilon_{\rm candChoice}
=

P\left(
c_{\rm reco}^{*}
\leftrightarrow
c_{\rm gen}^{*}
\mid
\text{event has reconstructable target objects}
\right).
$$

其中 $c_{\rm gen}^{*}$ 是生成层面按 nominal rule 定义的目标候选，$c_{\rm reco}^{*}$ 是重建层面按 best-score rule 选出的最终候选。

引入 candChoice 的原因是：

$$
\text{目标对象被重建}
\not\Rightarrow
\text{目标对象被选为 best candidate}.
$$

在普通 object efficiency 中，我们关心的是：

$$
P(\mu,K,J/\psi,\phi\ \text{被重建并通过选择}
\mid
\text{gen target system}).
$$

但在本分析中，还必须关心：

$$
P(\text{通过选择并最终进入直方图的候选就是 nominal target candidate}).
$$

这就是 candChoice 的角色。

它主要包含四类效应：

1. 多个 gen $\phi$ 之间的竞争；
2. 多个 reco $K^+K^-$ 组合之间的竞争；
3. detector smearing 导致的 best-score 排序翻转；
4. vertex、HLT、dikaon selection 等 event-level selection 与 candidate identity 的耦合。

因此，candChoice 可以不一定作为独立乘法因子写入最终效率，但必须在 closure test 和 systematic study 中显式监控。

---

#### 4. 微分截面中 bin-by-bin correction 的根本问题

如果我们用 reco-level best-score candidate 的动力学量给分子分 bin，用 gen-level best-score candidate 的动力学量给分母分 bin，则得到的是一个 effective bin-by-bin correction factor：

$$
\epsilon_i^{\rm eff}
=

\frac{
N\left(x_{\rm reco}(c_{\rm reco}^{*})\in i\right)
}{
N\left(x_{\rm gen}(c_{\rm gen}^{*})\in i\right)
}
$$

如果不存在 bin migration，则这个量可以近似看成第 (i) 个 bin 的效率。但如果 gen-to-reco response matrix 存在非对角项，则有

$$
N_i^{\rm reco}
=

\sum_j R_{ji}N_j^{\rm gen},
$$

其中

$$
R_{ji}
=

P(x_{\rm reco}\in i\mid x_{\rm gen}\in j).
$$

于是

$$
\epsilon_i^{\rm eff}
=

\frac{N_i^{\rm reco}}{N_i^{\rm gen}}

=

\frac{\sum_j R_{ji}N_j^{\rm gen}}{N_i^{\rm gen}}.
$$

将对角项和非对角项分开：

$$
\epsilon_i^{\rm eff}
=

R_{ii}
+
\sum_{j\neq i}R_{ji}
\frac{N_j^{\rm gen}}{N_i^{\rm gen}}.
$$

这说明，只要 (R_{ji}) 的非对角项不可忽略，(\epsilon_i^{\rm eff}) 就会显式依赖 MC 中的 gen-level shape：

$$
\frac{N_j^{\rm gen}}{N_i^{\rm gen}}.
$$

因此它不再是一个模型无关的 detector efficiency，而是一个把 efficiency、candidate-choice migration 和动力学分布形状混合在一起的 **effective correction factor**。

这正是本问题的核心。

---

#### 5. best-score candidate 作为 nominal definition 是否合理？

合理，但必须配套 response/closure 检查。

best-score rule 的优点是：

$$
c^{*}
=

\arg\max S(c)
$$

是确定的、可复现的，并且和数据端实际画图策略一致。问题不在于 best-score 本身，而在于：

$$
c_{\rm gen}^{*}
\to
c_{\rm reco}^{*}
$$

不是严格的一一对应映射。

因此 nominal definition 可以设为：

$$
c_{\rm gen}^{*}
=

\arg\max_{c\in \mathcal{C}_{\rm gen}^{\rm fid}} S(c),
$$

$$
c_{\rm reco}^{*}
=

\arg\max_{c\in \mathcal{C}_{\rm reco}^{\rm pass}} S(c).
$$

也就是说，GEN 和 RECO 两端都使用同一个 best-score concept。但随后必须研究：

$$
R_{ji}
=

P\left(
x_{\rm reco}(c_{\rm reco}^{*})\in i
\mid
x_{\rm gen}(c_{\rm gen}^{*})\in j
\right).
$$

如果 (R) 近似对角，则 bin-by-bin correction 可以作为 nominal。
如果 (R) 有明显非对角项，则必须考虑 unfolding、forward-folding，或者把对应的模型依赖作为系统误差。

---

#### 6. 当前建议的 nominal 方案

建议将测量对象定义为 event-level fiducial cross section：

$$
pp\to J/\psi J/\psi\phi+X,
$$

其中 (X) 允许包含额外的 $\phi$ 或其他软 QCD 活动。分析不是试图识别“硬散射中的唯一 $\phi$”，而是定义：

> 在 fiducial phase space 内存在至少两个 $J/\phi$ 和至少一个 $\phi$，并按照统一的 best-score rule 在 GEN 和 RECO 层面各选出一个代表性 $J/\psi J/\psi\phi$ candidate。

GEN 层面：

$$
N_{J/\psi}^{\rm fid}\ge 2,\qquad
N_{\phi}^{\rm fid}\ge 1,
$$

并定义

$$
c_{\rm gen}^{*}
=

\arg\max_{c\in \mathcal{C}_{\rm gen}^{\rm fid}}S(c).
$$

RECO 层面：

$$
c_{\rm reco}^{*}
=

\arg\max_{c\in \mathcal{C}_{\rm reco}^{\rm pass}}S(c).
$$

效率或响应定义为：

$$
R_{ji}
=

P(c_{\rm reco}^{*}\in i\mid c_{\rm gen}^{*}\in j).
$$

在这种定义下，选到额外 $\phi$ 或 softer $\phi$ 并不是逻辑错误，而是 analysis response 的一部分。关键是它是否被 response matrix 和 closure test 正确描述。

---

#### 7. 推荐的 closure test 结构

##### 7.1 Inclusive event-yield closure

首先检查总量是否闭合：

$$
N_{\rm gen}^{\rm fid}
\overset{?}{\approx}
\sum_{\rm reco\ selected}
w(c_{\rm reco}^{*}).
$$

如果 inclusive 总量都不闭合，则说明效率定义或 matching 逻辑存在根本问题。

####### 7.2 Differential closure

对每个微分变量 (x) 检查：

$$
N_{\rm gen}^{\rm fid}(x_i)
\overset{?}{\approx}
\sum_{c_{\rm reco}^{*}\in x_i}
w(c_{\rm reco}^{*}).
$$

这里尤其要检查：

$$
p_T(\phi),\quad
y(\phi),\quad
m(J/\psi J/\psi\phi),\quad
p_T(J/\psi J/\psi\phi).
$$

如果这些变量不闭合，而 (J/\psi J/\psi) 相关变量闭合，说明问题主要来自 $\phi$ candidate choice。

##### 7.3 Candidate-choice closure

定义正确选择率：

$$
f_{\rm correctChoice}(x)
=

\frac{
N(c_{\rm reco}^{*}\leftrightarrow c_{\rm gen}^{*})
}{
N(c_{\rm reco}^{*}\ \text{exists and passes})
}.
$$

并研究它随以下变量的变化：

$$
N_\phi^{\rm gen},\quad
p_T(\phi),\quad
m(J/\psi J/\psi\phi),\quad
\Delta S/S,\quad
p_T(J/\psi J/\psi\phi).
$$

其中

$$
\Delta S
=

S(c_{\rm gen}^{*})-S(c_{\rm gen}^{(2)}).
$$

如果 (\Delta S) 很小时 mismatch 比例高，这是预期的；但如果 (\Delta S) 很大时仍然 mismatch 明显，则说明 best-score mapping 本身不稳定。

##### 7.4 Response-matrix closure

构造矩阵：

$$
R_{ji}
=

P(x_{\rm reco}\in i\mid x_{\rm gen}\in j).
$$

并检查 purity 和 stability：

$$
P_i
=

\frac{
N(x_{\rm gen}\in i,\ x_{\rm reco}\in i)
}{
N(x_{\rm reco}\in i)
},
$$

$$
S_i
=

\frac{
N(x_{\rm gen}\in i,\ x_{\rm reco}\in i)
}{
N(x_{\rm gen}\in i)
}.
$$

如果每个 bin 的 purity 和 stability 都足够高，bin-by-bin correction 可以接受。
如果某些 bin 的 purity/stability 很低，则这些 bin 需要合并、改用 response-matrix correction，或赋予额外系统误差。

---

#### 8. 对不同微分变量的处理建议

##### 8.1 较安全的变量

主要由两个 $J/\phi$ 决定的变量相对安全，例如：

$$
m(J/\psi J/\psi),\quad
p_T(J/\psi J/\psi),\quad
|\Delta y(J/\psi,J/\psi)|.
$$

这些变量对选错 $\phi$ 不直接敏感。candidate mismatch 主要影响 event selection，而不一定造成大幅 bin migration。

##### 8.2 高风险变量

直接包含 $\phi$ 的变量风险较高：

$$
p_T(\phi),\quad
y(\phi),\quad
m(J/\psi J/\psi\phi),\quad
p_T(J/\psi J/\psi\phi).
$$

尤其是

$$
m(J/\psi J/\psi\phi)
$$

因为换一个 $\phi$ 会直接改变三体质量。这个变量应优先检查 response matrix。如果非对角项明显，则不建议直接使用简单 bin-by-bin correction 作为最终结果。

---

#### 9. 系统误差建议

至少应考虑以下几类 variation：

##### 9.1 Truth-definition variation

比较三种定义：

1. hardest-$\phi$ truth；
2. any-eligible-$\phi$ truth；
3. best-score-$\phi$ truth。

三者得到的修正后结果差异可作为 candidate-choice/truth-definition systematic。

##### 9.2 Shape-reweighted closure

对 MC gen-level 分布进行 reweight，例如重加权：

$$
p_T(\phi),\quad
m(J/\psi J/\psi\phi),\quad
p_T(J/\psi J/\psi\phi),\quad
N_\phi^{\rm gen}.
$$

然后重复 closure。若 correction factor 对 reweighting 敏感，则说明 bin-by-bin correction 存在 MC-shape dependence。

##### 9.3 (N_\phi^{\rm gen}) 分组 closure

按

$$
N_\phi^{\rm gen}=1,\quad
N_\phi^{\rm gen}=2,\quad
N_\phi^{\rm gen}\ge 3
$$

分别检查 closure。如果多 $\phi$ 子样本不闭合，需要对多 $\phi$ 建模赋予系统误差。

---

#### 10. 当前推荐结论

当前最稳妥的解决路线是：

$$
\boxed{
\text{将 nominal measurement 定义为 event-level }J/\psi J/\psi\phi+X
\text{ fiducial measurement}
}
$$

而不是试图识别唯一的“硬散射 $\phi$”。

同时采用：

$$
\boxed{
\text{GEN 和 RECO 两端统一使用 best-score candidate definition}
}
$$

即：

$$
c_{\rm gen}^{*}
=

\arg\max_{c\in \mathcal{C}*{\rm gen}^{\rm fid}}S(c),
\qquad
c*{\rm reco}^{*}
=

\arg\max_{c\in \mathcal{C}_{\rm reco}^{\rm pass}}S(c).
$$

然后用 response matrix 描述：

$$
N_i^{\rm reco}
=

\sum_j R_{ji}N_j^{\rm gen}.
$$

若 (R) 近似对角，则可以使用 bin-by-bin correction，并通过 closure test 验证。
若 (R) 明显非对角，则 bin-by-bin correction 会依赖 MC shape，应改用 response-matrix unfolding/forward-folding，或至少将 shape-reweighted closure 的偏差作为系统误差。

一句话总结：

$$
\boxed{
\text{微分截面修正的对象不是“某个粒子是否被重建”，而是“最终进入图中的 best candidate 是否正确代表 fiducial gen candidate”。}
}
$$

在 $J/\psi J/\psi\phi$ 分析中，多 $\phi$ 和多 candidate 使这两件事不再等价。因此 candChoice 必须作为 analysis response 被显式定义、检查，并通过 closure test 或 response matrix 纳入最终效率修正。


