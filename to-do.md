# Agent Data Platform: 核心待办事项

## P0: 系统核心瓶颈 (Highest Priority)

- **[ ] 解决工具间“信息孤岛”问题**
  - **问题**: `browser_use` 等工具获取的数据，无法在下一步被 `microsandbox` 使用。
  - **方案**: 建立一个共享工作区 (如 `/tmp/agent_workspace/`)，让工具能读写文件来传递数据，并更新Prompt教导Agent使用。

- **[ ] 提升 `microsandbox` 服务的稳定性**
  - **问题**: 服务偶发性出现 `ConnectionRefusedError`，导致工具调用失败。
  - **方案**: 排查服务日志，增加健康检查和自动重启机制。

## P1: 系统优化 (Optimization)

- **[ ] 优化任务生成系统**
  - **目标**: 改进原子任务和综合任务的生成逻辑，以降低不必要的 Token 消耗。

- **[ ] 增加成本核算功能**
  - **目标**: 为任务合成系统增加 Token 消耗统计和成本计算功能。