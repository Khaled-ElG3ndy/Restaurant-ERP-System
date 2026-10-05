from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPayrollRuleOrder(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env["hr.salary.rule.category"].create(
            {
                "name": "Ordering Test Category",
                "code": "ORDER_TEST",
                "company_id": cls.env.company.id,
            }
        )
        cls.rules = cls.env["hr.salary.rule"]
        for index, sequence in enumerate((10, 20, 30), start=1):
            cls.rules |= cls.env["hr.salary.rule"].create(
                {
                    "name": f"Ordering Rule {index}",
                    "code": f"ORDER_RULE_{index}",
                    "sequence": sequence,
                    "category_id": cls.category.id,
                    "condition_select": "none",
                    "amount_select": "fix",
                    "company_id": cls.env.company.id,
                }
            )
        cls.structure = cls.env["hr.payroll.structure"].create(
            {
                "name": "Ordering Test Structure",
                "code": "ORDER_STRUCTURE",
                "company_id": cls.env.company.id,
                "parent_id": False,
                "rule_ids": [(6, 0, cls.rules.ids)],
            }
        )

    def _ordered_rule_ids(self):
        self.rules.invalidate_recordset(["sequence"])
        return self.structure.rule_ids.sorted(
            key=lambda rule: (rule.sequence, rule.id)
        ).ids

    def _with_structure(self, rule):
        return rule.with_context(
            payroll_rule_order_structure_id=self.structure.id
        )

    def test_move_up_and_down_swaps_adjacent_sequences(self):
        first, second, third = self.rules
        self.assertFalse(
            self._with_structure(second).action_move_up_in_payroll_structure()
        )
        self.assertEqual(
            self._ordered_rule_ids(),
            [second.id, first.id, third.id],
        )
        self.assertEqual((second.sequence, first.sequence), (10, 20))

        self.assertFalse(
            self._with_structure(second).action_move_down_in_payroll_structure()
        )
        self.assertEqual(
            self._ordered_rule_ids(),
            [first.id, second.id, third.id],
        )

    def test_boundary_move_returns_notification_without_changes(self):
        first, _second, third = self.rules
        first_result = self._with_structure(
            first
        ).action_move_up_in_payroll_structure()
        last_result = self._with_structure(
            third
        ).action_move_down_in_payroll_structure()

        self.assertEqual(first_result["tag"], "display_notification")
        self.assertEqual(last_result["tag"], "display_notification")
        self.assertEqual(self._ordered_rule_ids(), self.rules.ids)

    def test_boundary_arrows_are_hidden(self):
        first, _second, third = self.rules

        self.assertEqual(self.structure.hosny_first_rule_id, first)
        self.assertEqual(self.structure.hosny_last_rule_id, third)

        self._with_structure(first).action_move_down_in_payroll_structure()
        self.assertEqual(self.structure.hosny_first_rule_id, self.rules[1])
        self.assertEqual(self.structure.hosny_last_rule_id, third)

    def test_duplicate_sequences_are_normalized_before_move(self):
        first, second, third = self.rules
        second.sequence = first.sequence
        self._with_structure(second).action_move_up_in_payroll_structure()

        self.assertEqual(
            self._ordered_rule_ids(),
            [second.id, first.id, third.id],
        )
        self.assertEqual(len(set(self.rules.mapped("sequence"))), 3)

    def test_rule_must_belong_to_context_structure(self):
        unrelated_rule = self.env["hr.salary.rule"].create(
            {
                "name": "Unrelated Ordering Rule",
                "code": "UNRELATED_ORDER_RULE",
                "sequence": 40,
                "category_id": self.category.id,
                "condition_select": "none",
                "amount_select": "fix",
                "company_id": self.env.company.id,
            }
        )
        with self.assertRaises(UserError):
            self._with_structure(
                unrelated_rule
            ).action_move_up_in_payroll_structure()
