# DeepEye-SQL 实现差异分析报告

本文档详细对比了 DeepEye-SQL 论文描述的架构与当前代码库（MVP版本）的实现差异。

## 1. 总体架构 (Overall Architecture)

| 模块 | 论文描述 | 当前代码实现 | 差异/缺失 |
| :--- | :--- | :--- | :--- |
| **阶段划分** | 包含四个阶段：意图范围界定、N-版本生成、单元测试与修正、置信度感知选择。 | 基本框架已搭建，包含四个阶段的类结构。 | 结构一致，但各阶段内部实现深度有较大差距。 |

## 2. 阶段一：意图范围界定与语义落地 (Intent Scoping & Semantic Grounding)

### 2.1 语义值检索 (Semantic Value Retrieval)

*   **论文描述**：
    *   **离线预处理**：对 TEXT 类型列进行选择性抽取，使用 Embedding 模型（如 Qwen3-Embedding）生成向量，构建向量索引（Chroma + HNSW）。
    *   **在线检索**：提取问题关键词，并行在多列索引中检索 Top-K 相似值。
*   **当前实现 (`deepeye/value_retrieval.py`)**：
    *   **无离线阶段**：没有向量数据库，没有 Embedding 过程。
    *   **在线检索**：使用简单的 SQL `LIKE` 模糊匹配 (`WHERE col LIKE %keyword%`)。
    *   **关键词提取**：简单的长度启发式规则 (`len(w) > 3`)，而非 LLM 提取。
*   **差距分析**：**严重缺失**。当前实现无法处理语义相似但字面不同的情况（如 "USA" vs "United States"），且在大数据量下性能极差。

### 2.2 鲁棒模式链接 (Robust Schema Linking)

*   **论文描述**：
    *   **三种策略**：直接链接 (Direct)、反向链接 (Reversed, 解析 Draft SQL)、基于值的链接 (Value-based)。
    *   **并集与闭包**：取三种结果的并集，并**强制执行关系闭包 (Relational Closure)**，即自动补全外键关联路径上的表。
*   **当前实现 (`deepeye/schema_linking.py`)**：
    *   **策略实现**：
        *   Direct: 已实现。
        *   Reversed: 使用 Skeleton 生成作为 Draft SQL 的代理，已实现。
        *   Value-based: 仅根据检索到的值的表名进行简单推断。
    *   **结果聚合**：实现了并集。
    *   **闭包处理**：**完全缺失**。没有解析外键关系并补全路径的逻辑。
*   **差距分析**：**中度缺失**。缺少关系闭包可能导致多表 JOIN 时缺少中间表，导致生成的 SQL 无法执行或逻辑错误。

## 3. 阶段二：N-版本 SQL 生成 (N-version Programming for SQL Generation)

*   **论文描述**：采用三种不同的生成器并行生成，增加多样性。
*   **当前实现 (`deepeye/generators.py`)**：实现了三个生成器类，但内部逻辑简化。

### 3.1 Skeleton-based Generator
*   **论文**：组件分析 -> Skeleton 生成 -> 槽位填充。
*   **代码**：Skeleton 生成 -> 填充。
*   **差距**：基本符合，流程略有简化。

### 3.2 ICL-based Generator
*   **论文**：基于 DAIL-SQL 方法，动态检索相似的训练集案例（Schema-masked）作为 Few-shot 示例。
*   **代码**：使用**硬编码**的两个固定示例。
*   **差距**：**严重缺失**。缺乏动态检索能力，无法利用 Few-shot 提升复杂问题的泛化能力。

### 3.3 Divide-and-Conquer (D&C) Generator
*   **论文**：递归分解问题 -> 解决子问题 -> 组合答案。
*   **代码**：仅通过 Prompt 指示 LLM 内部进行"分治"思考，没有代码层面的递归调用或子问题拆解执行。
*   **差距**：**中度缺失**。依赖模型自身的推理能力，而非框架层面的分治调度。

## 4. 阶段三：单元测试与修正 (SQL Unit Testing and Revision)

*   **论文描述**：
    *   **工具链 (Tool-Chain)**：包含一系列确定性检查器（Syntax, JOIN, ORDER-BY, Time, SELECT, MaxMin, NULL, Result）。
    *   **流程**：顺序检查，发现错误即暂停并调用 LLM 根据错误指令修正。
*   **当前实现 (`deepeye/checkers.py`)**：
    *   **检查器**：仅实现了 `SyntaxChecker` (基于 sqlglot) 和 `JoinChecker` (简单的 "JOIN 必须有 ON" 检查)。
    *   **缺失检查器**：
        *   `TimeChecker`: 检查时间格式函数。
        *   `OrderByChecker`: 检查 ORDER BY + LIMIT 逻辑。
        *   `SelectChecker`: 消除 `SELECT *`。
        *   `MaxMinChecker`: 优化极值查询。
        *   `NullChecker`: 检查 NULL 值陷阱。
        *   `ResultChecker`: 检查空结果或无意义结果。
*   **差距分析**：**严重缺失**。大部分特定的语义和逻辑检查器未实现，无法发挥 Tool-Chain 的核心纠错优势。

## 5. 阶段四：置信度感知选择 (Confidence-aware Selection)

*   **论文描述**：
    *   **聚类**：基于执行结果聚类。
    *   **置信度**：最大簇占比。
    *   **高置信度**：直接输出。
    *   **低置信度**：**非平衡投票 (Unbalanced Voting)**。
        *   **认知先验 (Cognitive Prior)**：告知 LLM 哪个 SQL 置信度更高。
        *   **成对裁决 (Pairwise Adjudication)**：多次采样投票，计算胜率。
        *   **综合打分**：置信度 * 胜率。
*   **当前实现 (`deepeye/selection.py`)**：
    *   **聚类与置信度**：已实现。
    *   **选择逻辑**：阈值判断已实现。
    *   **低置信度处理**：仅实现了简单的 A/B 投票，取 Top-2 簇的一个代表进行一次比较。
    *   **缺失**：没有"认知先验"提示，没有计算"胜率"（Win Rate），没有综合打分公式。
*   **差距分析**：**中度缺失**。投票机制过于简化，可能无法在低置信度场景下选出最佳答案。

## 总结与建议

当前代码库是一个**功能原型 (MVP)**，验证了 DeepEye-SQL 的基本流程（Pipeline），但在核心算法的深度和工程细节上与论文描述有显著差距。

**后续开发优先级建议：**

1.  **P0 (高危)**: 完善 **Schema Linking 的闭包 (Closure)** 逻辑，否则多表查询极易失败。
2.  **P0 (高危)**: 补充 **Checkers**，特别是 `ResultChecker` 和 `NullChecker`，这是提升可靠性的关键。
3.  **P1 (核心)**: 实现基于向量数据库的 **Value Retrieval**，这是解决实体识别问题的基础。
4.  **P1 (核心)**: 实现 **ICL 动态示例检索**，这对提升生成质量至关重要。
5.  **P2 (优化)**: 完善 Selection 阶段的非平衡投票逻辑。
