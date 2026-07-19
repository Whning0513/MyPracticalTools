# ACA 数据集与 DataPackage 设计

## 目标

构建一个可直接用于训练、评估与个性化代码修复/反例生成研究的数据集。每条提交都必须是一个真实、可重放的错误程序：它在同一题的 frozen testcase set 上既有 AC 又有非 AC，且保留代码、输入、输出、判定和行覆盖证据。题目资产与提交资产分开管理，使同一题以后被再次采样时无需重复补齐或重复调用 API。

当前首个实验版本称为 **v0.2**：训练集 1,000 条、测试集 100 条，Python:C++ 为 4:6。训练/测试的题目、用户、源码 hash / canonical code id 必须完全不重合。

## 原始数据要求

### 提交级硬约束

- 来自 Step7 的可消费 mixed submission：correctness 完整、coverage 可用且与 correctness 重放一致、Step6 成功、候选覆盖行和有效未覆盖行均非空。
- 至少有 16 个 frozen case，且至少 2 个 AC、至少 2 个非 AC。
- 保留原始代码、语言、用户、题目、canonical code id/source hash、每个 case 的 input、expected output、actual output、final verdict、coverage bitmap，以及 candidate/effective uncovered lines。
- 同一 split 内不保留重复 source hash/canonical code；训练与测试间也不得重合。
- C++ 原始 stdout 缺失时允许 replay 补齐，但不得覆盖原始 Step4 verdict 或 case verdict；replay 相关字段必须独立保存。

### 切分与分布硬约束

- train/test 的 `problem_id` 零重合。
- train/test 的 `user_id` 零重合。
- train/test 的源码标识零重合。
- 不允许 singleton user 或 singleton problem；保留真实用户在同题上的短提交轨迹，避免人为复制。
- 语言比例固定为 Python:C++ = 4:6。

### 分布软目标

- 用户与题目的提交数不能极端集中，也不能被机械地均匀化。
- 难度、错误行为和题型尽量平滑、多样；同题的错误提交也应保持差异。
- 若软目标无法同时满足，优先保证全部硬约束，并在 manifest/report 中说明原因。

## Step4--7 的数据基础

Step4 运行 frozen cases，记录 correctness 与逐 case coverage；全 AC 和全非 AC 的提交不做 coverage，mixed 提交进入 coverage。Step6 在不删除原始未覆盖行的前提下，产出 `effective_uncovered_lines`：排除可跨语言对齐的未使用顶层函数/类、无意义常量初始化、IO、调试输出和控制流样板；解析失败回退原始未覆盖行并标记。Step7 不改写原记录，而是输出满足质量门槛的提交集合。

因此 DataPackage 不重新判断 Step4--7 的主结论，只补齐下游消费所需的可重放证据和题目资产。

## DataPackage

DataPackage 是可复用的发布流水线，而非一次性脚本。它有两个逻辑步骤。

### Step1：补齐提交集 replay

Step1 只补提交资产，不改题目资产，也不重筛数据。

- Python/C：原始 stdout 已完整，直接解析为统一消费字段 `actual_stdout_resolved`。
- C++：若原始 stdout 缺失，对该提交的**全部 frozen cases**独立进程重放；一次编译，但每个 case 独立目录、独立进程运行。
- 写入 `replay_stdout`、`replay_verdict`、`replay_verdict_drift`；不覆盖 `final_verdict`、原 stdout 或原 case verdict。
- replay 环境必须锁定并记录 compiler/version、compile flags、timeout、memory limit、sandbox version、judge mode 与输出比较规则。

Step1 验收：所有需要补跑的 C++ 提交，replay case 数等于 frozen case 数；每个 replay case 有 stdout 或明确的 timeout/runtime/no-output 状态；drift 数量明确记录；用户/题目/hash 隔离和去重仍成立。

### Step2：可复用题目资产库

Step2 建立按 `problem_id` 索引的题目资产库，资产跨语言复用，并采用惰性生产：已有资产先复用，缺失才补齐。每题固定以下评测定义：

`problem_id -> validator_hash, fixed_ref_hash, judge_rule, frozen testcase set`

实验开始后这些定义不得在线修改；发现问题时该题退出 certified set，而不是在线换 ref 或 validator。

#### Validator / judge

优先使用 CodeContests+ parquet 中提供的 testlib validator 源码，而不是凭 LLM 从题面臆造。validator 用于判断输入是否合法，frozen case 必须全部通过。若未来缺少官方 validator，才由强模型从题面生成候选 validator，并通过 malformed/boundary/structure fuzz QA。

树、连通、排列、互异、多测总和等可检查结构约束必须检查。若题面所称“保证存在解”本身接近求解，则记为 `semantic_unchecked/high_risk`，不要伪装成完整 validator；这种少量题可以直接不进入 certified set。

#### Fixed reference

已有 frozen cases 无需 ref 求答案；ref 用于新生成合法输入。候选来源可包括旧 ACA refs、多个 AC 提交、强模型代码或人工修复，但构建期必须解决分歧。最终每题只锁定一个 `fixed_ref`：它通过全部 frozen cases、边界/压力 case，并与其他高可信候选在压力 case 一致。它是 peer/constructed reference，不应称作 official reference。

#### Blind probes

blind probe 是构建期的难度探针，不是官方 testcase，也不会直接写入 certified frozen case set。流程为：

`Qwen blind generator -> validator -> fixed ref -> target submission replay`

只有 validator 接受且 fixed ref 正常运行的候选才参与提交级判定。每个 target submission 单独运行全部有效 probe；case 目录和进程彼此隔离。blind 输出记录 probe 数、有效 probe 数、countercase 数、首个证据及生成溯源。

同一轮模型生成的 probe 有相关性，因此不以单次命中直接删除提交：单次至三次命中是难度标签；4/5 持续命中才标记 `easily_hacked` 并从最终选择中排除。模型多次格式失败的极少数题不混入未筛查数据，而是从候选题池弃用。

## 输出包

v0.2 发布目录应至少包含：

- `train/submissions.jsonl.zst` 与 `test/submissions.jsonl.zst`：最终 Step1 完整提交集。
- `train/problems.jsonl.zst` 与 `test/problems.jsonl.zst`：对应的完整题目资产，包括题干、frozen cases、validator、fixed ref 和 judge 定义。
- blind gate 元数据：生成模型/提示版本、每提交的 probe 统计、countercase 统计和排除状态。
- `manifest.json`：版本、随机种子、语言与数量配额、质量门槛、环境版本、资产 hash。
- `audit/report.json`：切分隔离、singleton、source hash、replay drift、validator/ref 认证和 blind 筛查统计。

包内的题目资产必须能闭合：一个提交所引用的题目、frozen inputs、预期输出、validator、fixed ref 与 judge 规则均可在同一版本包中找到。

## 可信度边界

最可靠的是原始 frozen cases 与其 Step4 运行记录。testlib validator 是可执行的输入域定义。fixed ref 是构建期锁定的 constructed/peer reference，不是假冒官方解答。blind probes 用于难度标注和异常提交筛除，不改变原始 benchmark 判定。所有这些层次必须在字段和文档中明确区分。

## 产出数据集 SOP

1. **冻结输入。** 指定 Step7 提交源、题目源、目标语言比例、train/test 数量、随机种子和质量门槛；写入版本化配置。不得在运行中修改配额或混入未声明数据源。
2. **建立过载候选池。** 从 Step7 流式抽取约 120% 的候选，先做 correctness/coverage/Step6/code-hash 质量门槛，再确保候选层面的 user/problem/code 隔离和无 singleton。候选不足则失败，不用复制或合成提交填充。
3. **补齐并认证题目资产。** 对候选题查资产库；优先导入 CodeContests+ 的 testlib validator 和已验证 ref。验证 validator 接受全部 frozen cases，验证 fixed ref 通过全部 frozen cases；失败题标记并从候选池移除。记录 validator/ref hash 与运行环境。
4. **生成与验证 blind probes。** 用固定模型、提示版本和生成参数为每题生成候选输入；格式失败可有限重试，持续失败的题直接移除。每个输入依次过 validator、fixed ref，只有二者成功才成为有效 probe。
5. **提交级 blind gate。** 对每个有效 probe、每个候选提交独立进程运行；保存命中数量、首个 countercase 和 stderr。按发布版本的明确阈值标记 `easily_hacked`，不覆盖 Step4 原始 verdict。
6. **一次性最终抽样。** 仅从已认证题、已完成 blind gate、且未标记 `easily_hacked` 的候选中抽取目标 1000/100；再次强制 train/test 的 user、problem、code hash 零重合与语言配额。若硬约束不可满足，报告不足并扩大下一版候选池；不得悄悄放松约束或在线补样本。
7. **运行 Step1 replay。** 对最终选择中 stdout 缺失的 C++ 提交执行一次编译、case 级独立重放；写 replay 字段和 drift，不改原记录。Python/C 不做无意义重跑。
8. **组装发布包。** 写 train/test 提交集、闭合题目集、blind 元数据、validator/ref、运行环境锁定信息、manifest 和 audit report；所有流式文件压缩后记录 SHA-256。
9. **最终验收。** 检查数量与语言比例、三类隔离、无 singleton、source hash 去重、每个提交题目资产闭合、replay 完整性/drift、validator/ref 认证、blind 筛查覆盖及压缩包 hash。抽取若干提交人工复核代码、case、stdout、verdict、coverage 和未覆盖行之间是否一致。
10. **发布后冻结。** 将版本目录设为只读事实来源；后续修复或扩大数据只能创建新的版本号和新的 manifest，不能回写旧版本。
