"""Hard eval cases: adversarial stress tests for weak points.

Four categories target specific flaws the review flagged:

- semantic_conflict_*  — fact A replaced by fact B without any negation word.
  ConflictDetector's negation-heuristic cannot catch these. Tests whether
  the paging/retrieval pipeline surfaces the latest decision.
- distractor_keyword_* — correct fact sits next to a plausible-but-wrong
  keyword (same topic, different slot). Tests whether the answer layer
  discriminates beyond simple string overlap.
- state_evolution_*    — fact revised 2-3 times. Only the latest revision
  should be recalled; earlier versions must appear as forbidden_facts.
- restatement_dedup_*  — same fact stated three different ways. Tests
  whether heuristic paging deduplicates or stores redundant facts.

Cases intentionally avoid the update markers used by the heuristic pager
("更新", "改为", "搬到", ...) in their "new" statements so that the old
fact is not automatically down-ranked. This is what makes the cases hard.
"""

from memoryos_lite.schemas import EvalCase, MessageCreate, Role

HARD_CASE_COUNT = 16


def hard_cases() -> list[EvalCase]:
    """Return all hard adversarial cases (16 total, 4 per category)."""
    cases: list[EvalCase] = []
    cases.extend(_semantic_conflict_cases())
    cases.extend(_distractor_keyword_cases())
    cases.extend(_state_evolution_cases())
    cases.extend(_restatement_dedup_cases())
    return cases


def _semantic_conflict_cases() -> list[EvalCase]:
    """Fact A replaced by fact B without negation words."""
    return [
        EvalCase(
            case_id="semantic_conflict_db_001",
            conversation=[
                MessageCreate(role=Role.USER, content="项目技术选型：数据库选 PostgreSQL。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录数据库选型。"),
                MessageCreate(role=Role.USER, content="继续看 ORM 文档。"),
                MessageCreate(
                    role=Role.USER,
                    content="评审会后结论：数据库改用 MySQL 以简化运维。",
                ),
                MessageCreate(role=Role.ASSISTANT, content="已记录选型调整。"),
                MessageCreate(role=Role.USER, content="配置连接池。"),
            ],
            question="项目当前的数据库是什么？",
            expected_facts=["MySQL"],
            forbidden_facts=["PostgreSQL"],
            required_sources=["semantic_conflict_db_001_msg_004"],
        ),
        EvalCase(
            case_id="semantic_conflict_cache_001",
            conversation=[
                MessageCreate(role=Role.USER, content="架构评审：缓存层选 Redis。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录缓存层选型。"),
                MessageCreate(role=Role.USER, content="部署 Redis cluster。"),
                MessageCreate(
                    role=Role.USER,
                    content="压测结果出来，缓存层切换到 Memcached。",
                ),
                MessageCreate(role=Role.ASSISTANT, content="已记录切换。"),
                MessageCreate(role=Role.USER, content="写迁移脚本。"),
            ],
            question="缓存层用什么组件？",
            expected_facts=["Memcached"],
            forbidden_facts=["Redis"],
            required_sources=["semantic_conflict_cache_001_msg_004"],
        ),
        EvalCase(
            case_id="semantic_conflict_rpc_001",
            conversation=[
                MessageCreate(role=Role.USER, content="架构设计：RPC 框架用 gRPC。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录 RPC 框架。"),
                MessageCreate(role=Role.USER, content="写 proto 文件。"),
                MessageCreate(
                    role=Role.USER,
                    content="与合作团队对接，RPC 框架采用 Thrift。",
                ),
                MessageCreate(role=Role.ASSISTANT, content="已记录调整。"),
                MessageCreate(role=Role.USER, content="改接口定义。"),
            ],
            question="RPC 框架用什么？",
            expected_facts=["Thrift"],
            forbidden_facts=["gRPC"],
            required_sources=["semantic_conflict_rpc_001_msg_004"],
        ),
        EvalCase(
            case_id="semantic_conflict_budget_001",
            conversation=[
                MessageCreate(role=Role.USER, content="客户初步报价：预算 5 万美元。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录报价。"),
                MessageCreate(role=Role.USER, content="准备技术方案。"),
                MessageCreate(
                    role=Role.USER,
                    content="客户把预算调整到 3 万欧元。",
                ),
                MessageCreate(role=Role.ASSISTANT, content="已记录新预算。"),
                MessageCreate(role=Role.USER, content="重新出方案。"),
            ],
            question="客户当前的预算是多少？",
            expected_facts=["3 万欧元"],
            forbidden_facts=["5 万美元"],
            required_sources=["semantic_conflict_budget_001_msg_004"],
        ),
    ]


def _distractor_keyword_cases() -> list[EvalCase]:
    """Correct fact buried next to a plausible-but-wrong keyword."""
    return [
        EvalCase(
            case_id="distractor_district_001",
            conversation=[
                MessageCreate(role=Role.USER, content="家住在深圳南山区。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录住址。"),
                MessageCreate(role=Role.USER, content="公司在深圳福田区。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录办公地。"),
                MessageCreate(role=Role.USER, content="通勤大约 40 分钟。"),
                MessageCreate(role=Role.USER, content="周末常去海边。"),
            ],
            question="我家住在深圳哪个区？",
            expected_facts=["南山"],
            forbidden_facts=["福田"],
            required_sources=["distractor_district_001_msg_001"],
        ),
        EvalCase(
            case_id="distractor_db_overlap_001",
            conversation=[
                MessageCreate(role=Role.USER, content="项目技术栈：PostgreSQL + Redis + Kafka。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录技术栈。"),
                MessageCreate(role=Role.USER, content="优化查询性能。"),
                MessageCreate(
                    role=Role.USER,
                    content="分析型场景下，PostgreSQL 换 DuckDB。",
                ),
                MessageCreate(role=Role.ASSISTANT, content="已记录调整。"),
                MessageCreate(role=Role.USER, content="Redis 和 Kafka 保留。"),
            ],
            question="当前分析型查询用哪个数据库？",
            expected_facts=["DuckDB"],
            forbidden_facts=["PostgreSQL"],
            required_sources=["distractor_db_overlap_001_msg_004"],
        ),
        EvalCase(
            case_id="distractor_language_001",
            conversation=[
                MessageCreate(role=Role.USER, content="I prefer Java for services."),
                MessageCreate(role=Role.ASSISTANT, content="已记录偏好。"),
                MessageCreate(role=Role.USER, content="写了一些 demo。"),
                MessageCreate(
                    role=Role.USER,
                    content="经过评估，服务端我选 Kotlin。",
                ),
                MessageCreate(role=Role.ASSISTANT, content="已记录语言选择。"),
                MessageCreate(role=Role.USER, content="准备搭脚手架。"),
            ],
            question="服务端使用什么编程语言？",
            expected_facts=["Kotlin"],
            forbidden_facts=["Java"],
            required_sources=["distractor_language_001_msg_004"],
        ),
        EvalCase(
            case_id="distractor_role_001",
            conversation=[
                MessageCreate(role=Role.USER, content="团队分工：小王负责后端。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录分工。"),
                MessageCreate(role=Role.USER, content="小李负责前端。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录分工。"),
                MessageCreate(role=Role.USER, content="下周架构评审。"),
                MessageCreate(role=Role.USER, content="周会安排中。"),
            ],
            question="谁负责前端开发？",
            expected_facts=["小李"],
            forbidden_facts=["小王"],
            required_sources=["distractor_role_001_msg_003"],
        ),
    ]


def _state_evolution_cases() -> list[EvalCase]:
    """Fact revised two to three times; only the latest counts."""
    return [
        EvalCase(
            case_id="state_evolution_deadline_001",
            conversation=[
                MessageCreate(role=Role.USER, content="项目截止日期定 10 月 15 日。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录截止日期。"),
                MessageCreate(role=Role.USER, content="截止日期延到 10 月 22 日。"),
                MessageCreate(role=Role.USER, content="进度还是紧。"),
                MessageCreate(
                    role=Role.USER,
                    content="截止日期最终确定 11 月 1 日。",
                ),
                MessageCreate(role=Role.ASSISTANT, content="已记录最终截止日期。"),
            ],
            question="项目最终截止日期是哪天？",
            expected_facts=["11 月 1"],
            forbidden_facts=["10 月 15", "10 月 22"],
            required_sources=["state_evolution_deadline_001_msg_005"],
        ),
        EvalCase(
            case_id="state_evolution_stack_001",
            conversation=[
                MessageCreate(role=Role.USER, content="技术栈初步定 Python。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录技术栈。"),
                MessageCreate(role=Role.USER, content="性能测试后，技术栈切到 Go。"),
                MessageCreate(role=Role.USER, content="继续搭环境。"),
                MessageCreate(
                    role=Role.USER,
                    content="综合评估后，技术栈最终确定 Rust。",
                ),
                MessageCreate(role=Role.ASSISTANT, content="已记录最终技术栈。"),
            ],
            question="项目最终的技术栈是什么？",
            expected_facts=["Rust"],
            forbidden_facts=["Python", "Go"],
            required_sources=["state_evolution_stack_001_msg_005"],
        ),
        EvalCase(
            case_id="state_evolution_meeting_001",
            conversation=[
                MessageCreate(role=Role.USER, content="周会定在 A101 会议室。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录会议室。"),
                MessageCreate(role=Role.USER, content="A101 被占，会议室调到 B203。"),
                MessageCreate(role=Role.USER, content="发了通知。"),
                MessageCreate(
                    role=Role.USER,
                    content="B203 维护，会议室最终换 C505。",
                ),
                MessageCreate(role=Role.ASSISTANT, content="已记录最终会议室。"),
            ],
            question="周会最终在哪个会议室开？",
            expected_facts=["C505"],
            forbidden_facts=["A101", "B203"],
            required_sources=["state_evolution_meeting_001_msg_005"],
        ),
        EvalCase(
            case_id="state_evolution_price_001",
            conversation=[
                MessageCreate(role=Role.USER, content="产品定价 $99 美元。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录定价。"),
                MessageCreate(role=Role.USER, content="市场反馈后，定价降到 $79 美元。"),
                MessageCreate(role=Role.USER, content="竞争激烈。"),
                MessageCreate(
                    role=Role.USER,
                    content="促销期，定价最终调整为 $49 美元。",
                ),
                MessageCreate(role=Role.ASSISTANT, content="已记录最终定价。"),
            ],
            question="产品最终定价是多少？",
            expected_facts=["$49"],
            forbidden_facts=["$99", "$79"],
            required_sources=["state_evolution_price_001_msg_005"],
        ),
    ]


def _restatement_dedup_cases() -> list[EvalCase]:
    """Same fact restated three different ways; tests paging dedup."""
    return [
        EvalCase(
            case_id="restatement_dedup_editor_001",
            conversation=[
                MessageCreate(role=Role.USER, content="我用 Vim 编辑代码。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录。"),
                MessageCreate(role=Role.USER, content="今天写了很多代码。"),
                MessageCreate(role=Role.USER, content="Vim 是我的首选编辑器。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录。"),
                MessageCreate(role=Role.USER, content="下班前配置插件。"),
                MessageCreate(role=Role.USER, content="我的编辑器一直固定用 Vim。"),
            ],
            question="我平时用什么编辑器？",
            expected_facts=["Vim"],
            forbidden_facts=["VSCode"],
            required_sources=["restatement_dedup_editor_001_msg_001"],
        ),
        EvalCase(
            case_id="restatement_dedup_coffee_001",
            conversation=[
                MessageCreate(role=Role.USER, content="我喜欢喝黑咖啡。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录偏好。"),
                MessageCreate(role=Role.USER, content="早上开会前准备一杯。"),
                MessageCreate(role=Role.USER, content="一直以来都喝黑咖啡，不加糖。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录。"),
                MessageCreate(role=Role.USER, content="买了新的咖啡豆。"),
                MessageCreate(role=Role.USER, content="我的咖啡习惯固定是黑咖啡无糖。"),
            ],
            question="我的咖啡偏好是什么？",
            expected_facts=["黑咖啡"],
            forbidden_facts=["拿铁"],
            required_sources=["restatement_dedup_coffee_001_msg_001"],
        ),
        EvalCase(
            case_id="restatement_dedup_commute_001",
            conversation=[
                MessageCreate(role=Role.USER, content="通勤我坐地铁。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录。"),
                MessageCreate(role=Role.USER, content="今天地铁人多。"),
                MessageCreate(role=Role.USER, content="地铁是我主要的通勤方式。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录。"),
                MessageCreate(role=Role.USER, content="办了年卡。"),
                MessageCreate(role=Role.USER, content="每天固定坐地铁上下班。"),
            ],
            question="我平时怎么通勤？",
            expected_facts=["地铁"],
            forbidden_facts=["开车"],
            required_sources=["restatement_dedup_commute_001_msg_001"],
        ),
        EvalCase(
            case_id="restatement_dedup_diet_001",
            conversation=[
                MessageCreate(role=Role.USER, content="我是素食者。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录饮食偏好。"),
                MessageCreate(role=Role.USER, content="外卖点蔬菜套餐。"),
                MessageCreate(role=Role.USER, content="吃素已经好几年了。"),
                MessageCreate(role=Role.ASSISTANT, content="已记录。"),
                MessageCreate(role=Role.USER, content="研究新食谱。"),
                MessageCreate(role=Role.USER, content="饮食上我固定吃素。"),
            ],
            question="我的饮食习惯是什么？",
            expected_facts=["素食"],
            forbidden_facts=["烤肉"],
            required_sources=["restatement_dedup_diet_001_msg_001"],
        ),
    ]
