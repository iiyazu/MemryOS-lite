"""Well-formedness tests for hard adversarial eval cases."""

from memoryos_lite.evals_hard import HARD_CASE_COUNT, hard_cases
from memoryos_lite.schemas import Role

_NEGATION_MARKERS = (
    "更新",
    "改为",
    "搬到",
    "不再",
    "已经搬",
    "不住",
    "替换",
    "纠正",
    "其实",
    "不想",
    "不做",
    "不用",
    "取消",
    "放弃",
    "改做",
)


class TestHardCasesWellFormedness:
    def test_count(self):
        cases = hard_cases()
        assert len(cases) == HARD_CASE_COUNT == 16

    def test_case_ids_unique(self):
        ids = [c.case_id for c in hard_cases()]
        assert len(ids) == len(set(ids))

    def test_four_categories_present(self):
        ids = [c.case_id for c in hard_cases()]
        assert sum(1 for i in ids if i.startswith("semantic_conflict_")) == 4
        assert sum(1 for i in ids if i.startswith("distractor_")) == 4
        assert sum(1 for i in ids if i.startswith("state_evolution_")) == 4
        assert sum(1 for i in ids if i.startswith("restatement_dedup_")) == 4

    def test_expected_and_forbidden_nonempty(self):
        for case in hard_cases():
            assert case.expected_facts, f"{case.case_id} has empty expected_facts"
            assert case.forbidden_facts, f"{case.case_id} has empty forbidden_facts"

    def test_required_sources_reference_valid_msg_indices(self):
        for case in hard_cases():
            msg_count = len(case.conversation)
            for source_id in case.required_sources:
                prefix = f"{case.case_id}_msg_"
                assert source_id.startswith(prefix), (
                    f"{case.case_id}: source {source_id} has wrong prefix"
                )
                idx = int(source_id[len(prefix) :])
                assert 1 <= idx <= msg_count, (
                    f"{case.case_id}: source index {idx} out of range 1..{msg_count}"
                )

    def test_semantic_conflict_new_statement_lacks_negation_marker(self):
        """The whole point of semantic_conflict: no negation words in the new statement."""
        for case in hard_cases():
            if not case.case_id.startswith("semantic_conflict_"):
                continue
            assert case.required_sources, f"{case.case_id} must pin the new statement"
            new_idx = int(case.required_sources[0].rsplit("_", 1)[-1]) - 1
            new_text = case.conversation[new_idx].content
            for marker in _NEGATION_MARKERS:
                assert marker not in new_text, (
                    f"{case.case_id}: new statement contains negation marker "
                    f"'{marker}' — defeats the point of this category"
                )

    def test_forbidden_fact_present_in_early_message(self):
        """For A/B/C categories, the forbidden keyword must actually appear in history."""
        for case in hard_cases():
            if case.case_id.startswith("restatement_dedup_"):
                continue
            full_text = " ".join(m.content for m in case.conversation)
            for forbidden in case.forbidden_facts:
                assert forbidden in full_text, (
                    f"{case.case_id}: forbidden '{forbidden}' not present in "
                    f"conversation — no distractor to resist"
                )

    def test_question_nonempty_and_has_user_messages(self):
        for case in hard_cases():
            assert case.question.strip()
            assert any(m.role == Role.USER for m in case.conversation)
