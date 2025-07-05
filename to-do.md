
2、基于#gemini-2.5-flash-lite-preview-06-17和#gemini-2.5-flash-preview-05-20两个低成本模型，完善 system prompt 构建，增强 agent 系统稳定性和任务成功率；
3、完善原子任务和综合任务生成系统。严格限制原子任务只生成需要工具调用的任务，以减少 token 消耗。同样。完善任务合成系统token 消耗统计和价格核算功能。

5、进一步检查、测试 broswer use 的功能，debug