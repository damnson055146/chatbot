# CUQ 测试 - 本项目（Ulster University 标准）

## 来源
- CUQ 官方页面: https://www.ulster.ac.uk/research/topic/computer-science/artificial-intelligence/projects/cuq
- 问卷 PDF: https://www.ulster.ac.uk/__data/assets/pdf_file/0009/478809/Chatbot-Usability-Questionnaire.pdf
- 计算工具（Excel）: https://www.ulster.ac.uk/__data/assets/excel_doc/0010/478810/CUQ-Calculation-Tool.xlsx

## 概述
CUQ 是专为聊天机器人可用性评估设计的问卷。它与 SUS（System Usability Scale）可比，
可与 SUS 或其他可用性指标一起使用。

## 何时与如何使用
- 用于可用性测试的后测评估阶段。
- 可纸质或电子化（如网页问卷工具）发放。

## 量表
所有题目使用 5 点李克特量表：
1 = 非常不同意，2 = 不同意，3 = 中立，4 = 同意，5 = 非常同意。
奇数题为正向，偶数题为负向。

## 问卷（CUQ 原始题目中文翻译）
1. 聊天机器人的个性真实且有吸引力
2. 聊天机器人显得过于机械
3. 聊天机器人在初始设置时很友好
4. 聊天机器人显得非常不友好
5. 聊天机器人清晰地说明了其范围与用途
6. 聊天机器人没有任何关于其用途的说明
7. 聊天机器人易于导航
8. 使用聊天机器人时很容易感到困惑
9. 聊天机器人很好地理解了我
10. 聊天机器人无法识别我输入的很多内容
11. 聊天机器人回复有用、恰当且信息充分
12. 聊天机器人回复不相关
13. 聊天机器人能很好地应对任何错误或失误
14. 聊天机器人似乎无法处理任何错误
15. 聊天机器人非常容易使用
16. 聊天机器人非常复杂

## 计分（CUQ 使用指南）
1. 根据同意程度为每题赋值 1 到 5 分。
2. 计算奇数题总和。
3. 计算偶数题总和。
4. 奇数题总和减 8。
5. 用 40 减去偶数题总和。
6. 将步骤 4 与步骤 5 相加（得分为 64 分制）。
7. 转换为 0-100 分： (得分 / 64) * 100。

## 项目任务脚本（可选；不属于 CUQ）
1. 注册并登录。
2. 新建会话并提出一个领域问题。
3. 查看一次回答的引用/来源。
4. 对回答提交反馈。
5. 搜索过往会话并导出历史。
6. 上传文件并触发内容摄取。
7. 使用摄取内容提出追问。
8. （可选管理员）验证数据源并检查索引健康状态。

## 项目特定附加项（可选；不属于 CUQ）
A. 引用/来源清晰且易于查看。
B. 文件上传与内容摄取可靠。
C. 会话管理（重命名、置顶、归档、导出）易于使用。
D. 反馈与升级流程清晰。
E. 系统在搜索或流式输出时有明确提示。
F. 管理端的数据源与检索设置易于管理。

## 验证说明（来自 Ulster University CUQ 页面）
- 2019 年 8 月在 Ulster University 的 PhD 研究中完成验证。
- 26 名参与者评估 3 个聊天机器人（好/中/差）。
- 局限性：样本量较小，聊天机器人类型有限。

## 引用
Samuel Holmes, Anne Moorhead, Raymond Bond, Huiru Zheng, Vivien Coates, and Michael Mctear. 2019.
Usability testing of a healthcare chatbot: Can we use conventional methods to assess conversational user interfaces?
In Proceedings of the 31st European Conference on Cognitive Ergonomics (ECCE 2019), ACM, New York, NY, USA, 207-214.
https://doi.org/10.1145/3335082.3335094
