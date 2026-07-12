"""Advanced eval cases: multi-session state evolution scenarios.

These cases target scenarios where stateful memory management (paging + patching)
outperforms stateless vector retrieval:
- Fact override: old facts replaced by new ones
- Long conversation early recall: target fact buried under 15+ messages
- Cross-session profile: memory persists across sessions
"""

from memoryos_lite.schemas import EvalCase, MessageCreate, Role

ADVANCED_CASE_COUNT = 4


def advanced_cases() -> list[EvalCase]:
    cases: list[EvalCase] = []
    # --- fact_override: user updates a fact, only latest should be recalled ---
    for i in range(1, ADVANCED_CASE_COUNT + 1):
        cases.append(
            EvalCase(
                case_id=f"fact_override_{i:03d}",
                conversation=[
                    MessageCreate(role=Role.USER, content=f"第{i}次记录：我现在住在北京海淀区。"),
                    MessageCreate(role=Role.ASSISTANT, content="已记录你的住址。"),
                    MessageCreate(role=Role.USER, content="今天天气不错，适合散步。"),
                    MessageCreate(role=Role.USER, content="工作上在做后端开发。"),
                    MessageCreate(
                        role=Role.USER, content=f"第{i}次更新：我已经搬到上海浦东了，不住北京了。"
                    ),
                    MessageCreate(role=Role.ASSISTANT, content="已更新你的住址信息。"),
                    MessageCreate(role=Role.USER, content="周末打算去逛逛新家附近。"),
                ],
                question="我现在住在哪里？",
                expected_facts=["上海浦东"],
                forbidden_facts=["北京海淀"],
                required_sources=[f"fact_override_{i:03d}_msg_005"],
            )
        )

    # --- long_conversation_early_recall: target fact at position 2, buried under 15+ messages ---
    for i in range(1, ADVANCED_CASE_COUNT + 1):
        noise_messages = [
            MessageCreate(
                role=Role.USER, content=f"第{i}段噪声消息{j}：日常工作记录、会议安排、代码review。"
            )
            for j in range(1, 14)
        ]
        cases.append(
            EvalCase(
                case_id=f"long_conv_early_recall_{i:03d}",
                conversation=[
                    MessageCreate(role=Role.USER, content="开始新的对话。"),
                    MessageCreate(
                        role=Role.USER,
                        content=f"第{i}次记录：我的技术栈核心是 Rust + WebAssembly。",
                    ),
                    MessageCreate(role=Role.ASSISTANT, content="已记录技术栈。"),
                    *noise_messages,
                    MessageCreate(role=Role.USER, content="最近在看新的框架。"),
                ],
                question="我的核心技术栈是什么？",
                expected_facts=["Rust", "WebAssembly"],
                forbidden_facts=["Java", "Python"],
                required_fact_sources={
                    "Rust": [f"long_conv_early_recall_{i:03d}_msg_002"],
                    "WebAssembly": [f"long_conv_early_recall_{i:03d}_msg_002"],
                },
            )
        )

    # --- cross_session_profile: profile set in session 1, queried in session 2 ---
    for i in range(1, ADVANCED_CASE_COUNT + 1):
        cases.append(
            EvalCase(
                case_id=f"cross_session_profile_{i:03d}",
                conversation=[
                    MessageCreate(
                        role=Role.USER,
                        content=f"第{i}次自我介绍：我是一名5年经验的后端工程师，专注分布式系统。",
                    ),
                    MessageCreate(role=Role.ASSISTANT, content="已记录你的背景。"),
                    MessageCreate(role=Role.USER, content="今天的任务是优化数据库查询。"),
                ],
                question="我的职业背景是什么？",
                expected_facts=["后端工程师", "分布式系统"],
                forbidden_facts=["前端", "设计师"],
                required_fact_sources={
                    "后端工程师": [f"cross_session_profile_{i:03d}_msg_001"],
                    "分布式系统": [f"cross_session_profile_{i:03d}_msg_001"],
                },
                query_in_new_session=True,
                include_global_core=True,
            )
        )

    # --- fact_accumulation: multiple facts added over time, all should be recalled ---
    for i in range(1, ADVANCED_CASE_COUNT + 1):
        cases.append(
            EvalCase(
                case_id=f"fact_accumulation_{i:03d}",
                conversation=[
                    MessageCreate(
                        role=Role.USER, content=f"第{i}次记录偏好1：我喜欢用 Vim 编辑器。"
                    ),
                    MessageCreate(role=Role.ASSISTANT, content="已记录。"),
                    MessageCreate(role=Role.USER, content="今天写了很多代码。"),
                    MessageCreate(role=Role.USER, content=f"第{i}次记录偏好2：我偏好暗色主题。"),
                    MessageCreate(role=Role.ASSISTANT, content="已记录。"),
                    MessageCreate(role=Role.USER, content="准备下班了。"),
                    MessageCreate(
                        role=Role.USER, content=f"第{i}次记录偏好3：我习惯用 tmux 管理终端。"
                    ),
                ],
                question="我的工具偏好有哪些？",
                expected_facts=["Vim", "暗色主题", "tmux"],
                forbidden_facts=["VSCode", "亮色"],
                required_fact_sources={
                    "Vim": [f"fact_accumulation_{i:03d}_msg_001"],
                    "暗色主题": [f"fact_accumulation_{i:03d}_msg_004"],
                    "tmux": [f"fact_accumulation_{i:03d}_msg_007"],
                },
            )
        )

    return cases
