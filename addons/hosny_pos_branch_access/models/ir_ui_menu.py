from odoo import api, fields, models


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    _HOSNY_OPTIONAL_CASHIER_MENU_XMLIDS = (
        "project.menu_main_pm",
        "bi_hr_payroll.menu_hr_payroll_root",
        "hr_attendance.menu_hr_attendance_root",
        "project_todo.menu_todo_todos",
        "hr_holidays.menu_hr_holidays_root",
        "utm.menu_link_tracker_root",
        "base.menu_tests",
    )

    hosny_hide_for_cashier = fields.Boolean(
        string="Hidden for branch cashiers",
        default=False,
        help=(
            "Menus flagged here disappear for users restricted to a branch. "
            "Everybody else keeps seeing them, so managers and administrators "
            "are not affected."
        ),
    )
    hosny_hide_for_cashier_tree = fields.Boolean(
        compute="_compute_hosny_hide_for_cashier_tree",
        store=True,
        recursive=True,
        index=True,
    )

    @api.depends("hosny_hide_for_cashier", "parent_id.hosny_hide_for_cashier_tree")
    def _compute_hosny_hide_for_cashier_tree(self):
        for menu in self:
            menu.hosny_hide_for_cashier_tree = (
                menu.hosny_hide_for_cashier
                or menu.parent_id.hosny_hide_for_cashier_tree
            )

    @api.model
    def hosny_flag_optional_cashier_menus(self):
        menus = self.sudo()
        for xmlid in self._HOSNY_OPTIONAL_CASHIER_MENU_XMLIDS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                menus |= menu
        menus.write({"hosny_hide_for_cashier": True})
        return True
