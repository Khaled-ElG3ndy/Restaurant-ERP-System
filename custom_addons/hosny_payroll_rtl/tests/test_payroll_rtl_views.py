from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPayrollRtlViews(TransactionCase):
    def test_payroll_configuration_forms_have_rendered_rtl_sections(self):
        expected_sections = {
            "bi_hr_payroll.view_hr_employee_grade_form": (
                "//form/group[1]",
                "//form/notebook[1]",
            ),
            "bi_hr_payroll.hr_salary_rule_category_form": (
                "//form/group[1]",
                "//form/group[2]",
            ),
            "bi_hr_payroll.hr_salary_rule_form": (
                "//form/label[1]",
                "//form/h1[1]",
                "//form/label[2]",
                "//form/h2[1]",
                "//form/group[1]",
                "//form/notebook[1]",
            ),
            "bi_hr_payroll.hr_contribution_register_form": (
                "//form/group[1]",
                "//form/group[2]",
            ),
        }

        for view_xmlid, section_xpaths in expected_sections.items():
            with self.subTest(view=view_xmlid):
                arch = self.env.ref(view_xmlid)._get_combined_arch()
                for section_xpath in section_xpaths:
                    node = arch.xpath(section_xpath)[0]
                    classes = set((node.get("class") or "").split())
                    self.assertIn("o_hosny_payroll_rtl_section", classes)
