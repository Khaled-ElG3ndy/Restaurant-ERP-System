from datetime import date

from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHosnyHrWorkLocation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.jeddah = cls.env.ref("hosny_hr_work_location.work_location_jeddah")
        cls.madinah = cls.env.ref("hosny_hr_work_location.work_location_madinah")
        cls.riyadh = cls.env.ref("hosny_hr_work_location.work_location_riyadh")
        cls.employee_jeddah = cls.env["hr.employee"].create(
            {
                "name": "Jeddah Test Employee",
                "company_id": cls.company.id,
                "work_location_id": cls.jeddah.id,
            }
        )
        cls.employee_madinah = cls.env["hr.employee"].create(
            {
                "name": "Madinah Test Employee",
                "company_id": cls.company.id,
                "work_location_id": cls.madinah.id,
            }
        )

    def test_employee_uses_standard_model_and_only_branch_locations(self):
        field = self.env["hr.employee"]._fields["work_location_id"]
        self.assertEqual(field.comodel_name, "hr.work.location")
        selectable = self.env["hr.work.location"].search(
            [
                ("company_id", "=", self.company.id),
                ("hosny_branch_code", "in", ["jeddah", "madinah", "riyadh"]),
            ]
        )
        self.assertEqual(
            set(selectable.ids),
            {self.jeddah.id, self.madinah.id, self.riyadh.id},
        )

        customer = self.env["res.partner"].create(
            {"name": "Customer Must Not Be A Work Location", "customer_rank": 1}
        )
        vendor = self.env["res.partner"].create(
            {"name": "Vendor Must Not Be A Work Location", "supplier_rank": 1}
        )
        self.assertNotIn(customer.id, selectable.ids)
        self.assertNotIn(vendor.id, selectable.ids)
        self.assertEqual(
            self.employee_jeddah.address_id,
            self.jeddah.address_id,
        )

    def test_employee_form_hides_partner_field_and_limits_location_domain(self):
        view = self.env["hr.employee"].get_view(
            view_id=self.env.ref("hr.view_employee_form").id,
            view_type="form",
        )
        arch = etree.fromstring(view["arch"])
        address_nodes = arch.xpath(
            "//page[@name='work_information']//field[@name='address_id']"
        )
        location_nodes = arch.xpath(
            "//page[@name='work_information']//field[@name='work_location_id']"
        )
        self.assertTrue(address_nodes)
        self.assertEqual(address_nodes[0].get("invisible"), "1")
        self.assertTrue(location_nodes)
        self.assertIn("hosny_branch_code", location_nodes[0].get("domain"))
        self.assertIn("no_create", location_nodes[0].get("options"))

    def test_usual_week_location_field_applies_to_all_weekdays(self):
        employee = self.env["hr.employee"].new(
            {
                "name": "Weekly Location Test Employee",
                "company_id": self.company.id,
                "usual_week_location_id": self.jeddah.id,
            }
        )
        employee._onchange_usual_week_location_id()
        week_fields = employee._get_week_location_fields()
        self.assertTrue(
            all(employee[field_name] == self.jeddah for field_name in week_fields)
        )
        employee.sunday_location_id = self.madinah
        employee._compute_usual_week_location_id()
        self.assertFalse(employee.usual_week_location_id)
        employee.sunday_location_id = self.jeddah
        employee._compute_usual_week_location_id()
        self.assertEqual(employee.usual_week_location_id, self.jeddah)

    def test_usual_week_location_empty_value_does_not_clear_weekdays(self):
        employee = self.env["hr.employee"].create(
            {
                "name": "Weekly Location Persistence Test",
                "company_id": self.company.id,
                "usual_week_location_id": self.jeddah.id,
            }
        )
        week_fields = employee._get_week_location_fields()
        self.assertTrue(
            all(employee[field_name] == self.jeddah for field_name in week_fields)
        )

        employee.write({"thursday_location_id": self.madinah.id})
        self.assertFalse(employee.usual_week_location_id)
        self.assertEqual(employee.thursday_location_id, self.madinah)
        unchanged_fields = [field for field in week_fields if field != "thursday_location_id"]
        self.assertTrue(
            all(employee[field_name] == self.jeddah for field_name in unchanged_fields)
        )

        employee._inverse_usual_week_location_id()
        self.assertEqual(employee.thursday_location_id, self.madinah)
        self.assertTrue(
            all(employee[field_name] == self.jeddah for field_name in unchanged_fields)
        )

    def test_usual_week_location_form_is_arabic_and_limited(self):
        view = self.env["hr.employee"].get_view(
            view_id=self.env.ref("hr.view_employee_form").id,
            view_type="form",
        )
        arch = etree.fromstring(view["arch"])
        groups = arch.xpath("//group[@string='مكان العمل المعتاد']")
        self.assertTrue(groups)
        usual_location_nodes = arch.xpath("//field[@name='usual_week_location_id']")
        self.assertTrue(usual_location_nodes)
        self.assertIn("hosny_branch_code", usual_location_nodes[0].get("domain"))
        self.assertIn("no_create", usual_location_nodes[0].get("options"))

    def test_english_and_arabic_names(self):
        self.assertEqual(self.jeddah.with_context(lang="en_US").name, "Jeddah")
        self.assertEqual(self.madinah.with_context(lang="en_US").name, "Madinah")
        self.assertEqual(self.riyadh.with_context(lang="en_US").name, "Riyadh")
        self.assertEqual(self.jeddah.with_context(lang="ar_001").name, "جدة")
        self.assertEqual(self.madinah.with_context(lang="ar_001").name, "المدينة")
        self.assertEqual(self.riyadh.with_context(lang="ar_001").name, "الرياض")

    def test_new_company_gets_isolated_locations(self):
        other_company = self.env["res.company"].create(
            {"name": "Work Location Test Company"}
        )
        locations = self.env["hr.work.location"].search(
            [
                ("company_id", "=", other_company.id),
                ("hosny_branch_code", "in", ["jeddah", "madinah", "riyadh"]),
            ]
        )
        self.assertEqual(len(locations), 3)
        self.assertTrue(
            all(
                location.address_id.company_id == other_company
                for location in locations
            )
        )
        dynamic_xmlids = self.env["ir.model.data"].search(
            [
                ("module", "=", "hosny_hr_work_location"),
                ("name", "like", f"%_company_{other_company.id}"),
            ]
        )
        self.assertEqual(len(dynamic_xmlids), 6)
        self.assertTrue(all(dynamic_xmlids.mapped("noupdate")))

    def test_historical_work_entry_snapshot_and_grouping(self):
        entry_type = self.env["hr.work.entry.type"].search([], limit=1)
        entry_jeddah = self.env["hr.work.entry"].create(
            {
                "employee_id": self.employee_jeddah.id,
                "date": date.today(),
                "duration": 8,
                "work_entry_type_id": entry_type.id,
            }
        )
        entry_madinah = self.env["hr.work.entry"].create(
            {
                "employee_id": self.employee_madinah.id,
                "date": date.today(),
                "duration": 8,
                "work_entry_type_id": entry_type.id,
            }
        )
        self.assertEqual(entry_jeddah.work_location_id, self.jeddah)
        self.assertEqual(entry_madinah.work_location_id, self.madinah)

        self.employee_jeddah.work_location_id = self.madinah
        self.assertEqual(entry_jeddah.work_location_id, self.jeddah)

        new_entry = self.env["hr.work.entry"].create(
            {
                "employee_id": self.employee_jeddah.id,
                "date": date.today(),
                "duration": 4,
                "work_entry_type_id": entry_type.id,
            }
        )
        self.assertEqual(new_entry.work_location_id, self.madinah)

        grouped = self.env["hr.work.entry"]._read_group(
            [("id", "in", (entry_jeddah | entry_madinah | new_entry).ids)],
            ["work_location_id"],
            ["__count"],
        )
        counts = {location.id: count for location, count in grouped}
        self.assertEqual(counts[self.jeddah.id], 1)
        self.assertEqual(counts[self.madinah.id], 2)

    def test_payroll_leave_and_adjustment_snapshots(self):
        leave_type = self.env["hr.leave.type"].create(
            {
                "name": "Snapshot Test Leave",
                "requires_allocation": False,
                "request_unit": "day",
                "company_id": self.company.id,
            }
        )
        leave = self.env["hr.leave"].create(
            {
                "employee_id": self.employee_jeddah.id,
                "holiday_status_id": leave_type.id,
                "request_date_from": date.today(),
                "request_date_to": date.today(),
            }
        )
        payslip = self.env["hr.payslip"].create(
            {
                "employee_id": self.employee_jeddah.id,
                "contract_id": self.employee_jeddah.version_id.id,
                "company_id": self.company.id,
            }
        )
        adjustment = self.env["hosny.hr.salary.adjustment"].create(
            {
                "name": "Snapshot Test Adjustment",
                "employee_id": self.employee_jeddah.id,
                "version_id": self.employee_jeddah.version_id.id,
                "company_id": self.company.id,
                "amount": 100,
            }
        )
        self.assertEqual(leave.work_location_id, self.jeddah)
        self.assertEqual(payslip.work_location_id, self.jeddah)
        self.assertEqual(adjustment.work_location_id, self.jeddah)

        self.employee_jeddah.work_location_id = self.madinah
        self.assertEqual(leave.work_location_id, self.jeddah)
        self.assertEqual(payslip.work_location_id, self.jeddah)
        self.assertEqual(adjustment.work_location_id, self.jeddah)

        payslip.write({"work_location_id": self.madinah.id})
        self.assertEqual(payslip.work_location_id, self.jeddah)

    def test_internal_user_can_read_locations(self):
        user = self.env["res.users"].create(
            {
                "name": "Work Location Reader",
                "login": "work.location.reader@example.com",
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        records = self.env["hr.work.location"].with_user(user).search(
            [("hosny_branch_code", "!=", False)]
        )
        self.assertEqual(
            set(records.ids),
            {self.jeddah.id, self.madinah.id, self.riyadh.id},
        )

    def test_external_ids_are_unique(self):
        self.assertEqual(
            self.env["ir.model.data"].search_count(
                [
                    ("module", "=", "hosny_hr_work_location"),
                    ("name", "=", "work_location_jeddah"),
                ]
            ),
            1,
        )
        self.assertEqual(
            self.env["hr.work.location"].search_count(
                [
                    ("company_id", "=", self.company.id),
                    ("hosny_branch_code", "=", "jeddah"),
                ]
            ),
            1,
        )
