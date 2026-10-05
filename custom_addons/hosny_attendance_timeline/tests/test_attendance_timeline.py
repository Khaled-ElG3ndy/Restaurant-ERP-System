from datetime import datetime

from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAttendanceTimeline(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.attendance_model = cls.env["hr.attendance"].with_context(
            hosny_attendance_timeline_no_notify=True
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Timeline Employee",
                "company_id": cls.env.company.id,
                "ruleset_id": False,
            }
        )
        cls.attendance = cls.attendance_model.create(
            {
                "employee_id": cls.employee.id,
                "check_in": datetime(2026, 7, 6, 8, 0),
                "check_out": datetime(2026, 7, 6, 16, 0),
            }
        )

    def test_employee_and_attendance_payload(self):
        employee_payload = (
            self.attendance_model.get_timeline_employees(
                [("employee_id", "=", self.employee.id)]
            )
        )
        self.assertEqual(
            [employee["id"] for employee in employee_payload["employees"]],
            [self.employee.id],
        )
        self.assertTrue(employee_payload["permissions"]["create"])
        employee_data = employee_payload["employees"][0]
        self.assertEqual(employee_data["status"], "not_working")
        self.assertFalse(employee_data["is_checked_in"])
        self.assertFalse(employee_data["has_open_attendance"])
        self.assertIn("worked_today", employee_data)
        self.assertIn("overtime_today", employee_data)

        attendance_payload = (
            self.attendance_model.get_timeline_attendances(
                [("employee_id", "=", self.employee.id)],
                "2026-07-06 00:00:00",
                "2026-07-07 00:00:00",
                [self.employee.id],
            )
        )
        records = attendance_payload[str(self.employee.id)]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], self.attendance.id)
        self.assertEqual(records[0]["status"], "completed")
        self.assertEqual(
            records[0]["worked_hours"],
            self.attendance.worked_hours,
        )

    def test_range_excludes_unrelated_attendances(self):
        payload = self.attendance_model.get_timeline_attendances(
            [],
            "2026-07-07 00:00:00",
            "2026-07-08 00:00:00",
            [self.employee.id],
        )
        self.assertEqual(payload[str(self.employee.id)], [])

    def test_company_filter_is_mapped_to_employees(self):
        payload = self.attendance_model.get_timeline_employees(
            [("company_id", "=", self.env.company.id)]
        )
        self.assertIn(
            self.employee.id,
            [employee["id"] for employee in payload["employees"]],
        )

    def test_invalid_ranges_and_batches_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.attendance_model.get_timeline_attendances(
                [],
                "2026-07-01 00:00:00",
                "2026-09-01 00:00:00",
                [self.employee.id],
            )
        with self.assertRaises(ValidationError):
            self.attendance_model.get_timeline_attendances(
                [],
                "2026-07-01 00:00:00",
                "2026-07-02 00:00:00",
                list(range(1, 202)),
            )

    def test_explicit_employee_check_in_and_out_uses_core_action(self):
        result = (
            self.attendance_model
            .timeline_toggle_employee_attendance(
                self.employee.id, "check_in"
            )
        )
        attendance = self.attendance_model.browse(result["id"])
        self.assertEqual(attendance.employee_id, self.employee)
        self.assertTrue(attendance.check_in)
        self.assertFalse(attendance.check_out)

        result = (
            self.attendance_model
            .timeline_toggle_employee_attendance(
                self.employee.id, "check_out"
            )
        )
        self.assertEqual(result["id"], attendance.id)
        self.assertTrue(attendance.check_out)

        with self.assertRaises(UserError):
            (
                self.attendance_model
                .timeline_toggle_employee_attendance(
                    self.employee.id, "check_out"
                )
            )
        with self.assertRaises(ValidationError):
            (
                self.attendance_model
                .timeline_toggle_employee_attendance(
                    self.employee.id, "invalid"
                )
            )

    def test_officer_only_sees_managed_employees(self):
        officer = new_test_user(
            self.env,
            login="timeline_officer",
            groups="base.group_user",
        )
        managed_employee = self.env["hr.employee"].create(
            {
                "name": "Managed Timeline Employee",
                "attendance_manager_id": officer.id,
                "ruleset_id": False,
            }
        )
        other_employee = self.env["hr.employee"].create(
            {
                "name": "Other Timeline Employee",
                "attendance_manager_id": self.env.user.id,
                "ruleset_id": False,
            }
        )
        payload = self.env["hr.attendance"].with_user(
            officer
        ).get_timeline_employees(
            [
                (
                    "employee_id",
                    "in",
                    [managed_employee.id, other_employee.id],
                )
            ]
        )
        employee_ids = [
            employee["id"] for employee in payload["employees"]
        ]
        self.assertIn(managed_employee.id, employee_ids)
        self.assertNotIn(other_employee.id, employee_ids)
