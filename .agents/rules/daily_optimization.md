# NL2SQL 增量开发与每日优化规则 (Daily Optimization Rule)

当你在此工作区中启动会话，或用户提出“优化”、“更新”、“继续”等指令时，请自动执行以下标准迭代流程：

1. **读取任务清单**:
   - 查看 [task_backlog.md](file:///g:/project/NL2SQL/task_backlog.md) 文件。
   - 找到阶段 1 ~ 阶段 3 中**首个未完成 (`[ ]`)** 的 Task。

2. **代码实现**:
   - 按照 Task 目标在 `deepeye/` 对应模块中实现代码编写与重构。
   - 确保修改遵循模块化、高聚低耦原则，不破坏原有既有功能。

3. **测试验证**:
   - 运行测试或 `main.py`，确认逻辑正常运行且未发生报错。

4. **更新状态与提交**:
   - 将 [task_backlog.md](file:///g:/project/NL2SQL/task_backlog.md) 中的该 Task 标记为已完成 (`[x]`)。
   - 自动执行 `git add .` -> `git commit` -> `git push origin master` 将改动同步至 GitHub。
   - 输出简明报告向用户说明今日更新的模块及验证结果。
