# NL2SQL (DeepEye-SQL) 每日优化 Backlog 清单

本文档记录 NL2SQL 项目从 MVP 原型向 DeepEye-SQL 完整论文实现的增量优化任务列表。

## 📌 优化路线图 (Roadmap)

---

### 阶段 1：Schema Linking 与规则检查补全 (P0 - 高优先级)

- [x] **Task 1.1: Schema Linking 关系闭包 (Relational Closure)** (已于 2026-08-11 完成)
  - **目标**: 解析数据库中的 `FOREIGN KEY` 约束构建无向图/有向图，当选中的表不连通时，自动补全最短路径上的中间外键表。
  - **模块**: `deepeye/schema_linking.py`
  - **测试**: 验证跨表查询 (如 `students` -> `enrollments` -> `courses`) 在只指定 `students` 和 `courses` 时能自动补充 `enrollments` 表。

- [x] **Task 1.2: SQL 单元测试机制与 ResultChecker 实现** (已于 2026-08-24 完成)
  - **目标**: 在 SQLite 上试运行生成的 SQL，检测是否返回空集合、全 NULL 集合或导致句法错误，并返回改进建议。
  - **模块**: `deepeye/checkers.py`

- [x] **Task 1.3: NullChecker & SelectChecker 实现** (已于 2026-08-25 完成)
  - **目标**: 针对 `COUNT()` 与 `NULL` 陷阱进行确定性静态检查，移除 `SELECT *` 避免不必要的列暴露。
  - **模块**: `deepeye/checkers.py`

- [x] **Task 1.4: TimeChecker & OrderByChecker 实现** (已于 2026-08-26 完成)
  - **目标**: 针对时间格式化函数、`ORDER BY` 缺少 `LIMIT` 或字段歧义进行纠错提示。
  - **模块**: `deepeye/checkers.py`

---

### 阶段 2：语义检索与 ICL 动态增强 (P1 - 核心功能)

- [x] **Task 2.1: 向量化 Value Retrieval (Embedding + VectorDB)** (已于 2026-08-26 完成)
  - **目标**: 替代现有 SQL `LIKE` 模糊匹配，引入向量数据库与离线/在线 Embedding 索引，支持近义词实体检索（如 "USA" -> "United States"）。
  - **模块**: `deepeye/value_retrieval.py`

- [ ] **Task 2.2: 动态 ICL 示例检索 (DAIL-SQL 范式)**
  - **目标**: 摒弃硬编码 Few-shot 示例，构建 Schema-masked 检索索引，根据当前问题动态匹配 2-3 个最相似的真实 SQL 示例。
  - **模块**: `deepeye/generators.py`

- [ ] **Task 2.3: Divide-and-Conquer 生成器代码级任务拆解**
  - **目标**: 实现真实的代码级子问题递归拆解与子 SQL 拼接，而非仅依赖 Prompt 隐式推理。
  - **模块**: `deepeye/generators.py`

---

### 阶段 3：置信度感知选择与成对裁决 (P2 - 优化进阶)

- [ ] **Task 3.1: Selection 机制引入 Cognitive Prior 与 Win Rate 计算**
  - **目标**: 实现基于 Sampling 的 Pairwise Adjudication 比较，结合簇置信度和胜率综合打分选择最终 SQL。
  - **模块**: `deepeye/selection.py`

- [ ] **Task 3.2: 端到端 Benchmark 测试集与准确率评估脚本**
  - **目标**: 编写标准的评估脚本，量化系统在 Spider / BIRD 或自定义数据集上的 Execution Accuracy (EX)。
  - **模块**: `eval.py`
