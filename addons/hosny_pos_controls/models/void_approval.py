"""اعتماد إلغاء صنف بعد إرساله للمطبخ (طلب 2026-10-05).

بعد «إرسال الطلب» لا يحذف الكاشير صنفاً ولا ينقص كميته وحده: يكتب سبب الإلغاء،
ويعتمده حساب مفعَّل له «اعتماد إلغاء الأصناف المرسلة» بكلمة سر خاصة بهذا
الاعتماد (غير كلمة سر الدخول)، يضعها مدير النظام من شاشة المستخدم.

كلمة السر تُفحص هنا على الخادم فقط — لا تصل للمتصفح أبداً — وتُخزَّن مشفّرة
بنفس تشفير كلمات سر أودو. خمس محاولات خاطئة تقفل الحساب عن الاعتماد خمس دقائق.
كل اعتماد ناجح يُكتب في «سجل المراجعة» (pos.audit.log) ليراجعه المدير.
"""
import logging
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

MAX_FAILURES = 5
LOCK_MINUTES = 5


class ResUsers(models.Model):
    _inherit = "res.users"

    hosny_pos_void_approver = fields.Boolean(
        "اعتماد إلغاء الأصناف المرسلة (نقاط البيع)",
        groups="base.group_erp_manager",
        copy=False,
        help="يظهر اسمه في نافذة الإلغاء بنقطة البيع، ويعتمد بكلمة سر الإلغاء الخاصة به.",
    )
    hosny_pos_void_password = fields.Char(
        "كلمة سر الإلغاء",
        compute="_compute_hosny_pos_void_password",
        inverse="_inverse_hosny_pos_void_password",
        groups="base.group_erp_manager",
        help="غير كلمة سر الدخول. اكتب كلمة جديدة لتغييرها؛ تُحفظ مشفّرة ولا تُعرض.",
    )
    hosny_pos_void_password_hash = fields.Char(groups="base.group_system", copy=False)
    hosny_pos_void_password_set = fields.Boolean(
        "كلمة سر الإلغاء محفوظة",
        compute="_compute_hosny_pos_void_password",
        groups="base.group_erp_manager",
    )
    hosny_pos_void_failures = fields.Integer(groups="base.group_system", copy=False)
    hosny_pos_void_locked_until = fields.Datetime(groups="base.group_system", copy=False)

    def _compute_hosny_pos_void_password(self):
        for user in self:
            user.hosny_pos_void_password = False
            user.hosny_pos_void_password_set = bool(user.sudo().hosny_pos_void_password_hash)

    def _inverse_hosny_pos_void_password(self):
        for user in self:
            password = (user.hosny_pos_void_password or "").strip()
            if not password:
                continue
            user.sudo().write({
                "hosny_pos_void_password_hash": self._crypt_context().hash(password),
                "hosny_pos_void_failures": 0,
                "hosny_pos_void_locked_until": False,
            })


class PosAuditLog(models.Model):
    _inherit = "pos.audit.log"

    action = fields.Selection(
        selection_add=[("void_line", "إلغاء صنف بعد الإرسال")],
        ondelete={"void_line": "cascade"},
    )
    approved_by_user_id = fields.Many2one("res.users", "اعتمده", readonly=True)
    pos_config_id = fields.Many2one("pos.config", "نقطة البيع", readonly=True)
    order_ref = fields.Char("الطلب", readonly=True)
    order_uuid = fields.Char(readonly=True, index=True)
    table_name = fields.Char("الطاولة", readonly=True)
    product_name = fields.Char("الصنف", readonly=True)
    quantity_before = fields.Float("الكمية المرسلة", readonly=True)
    quantity_after = fields.Float("الكمية بعد الإلغاء", readonly=True)
    quantity_cancelled = fields.Float("الكمية الملغاة", readonly=True)

    @api.model
    def hosny_void_approvers(self, config_id=False):
        """أسماء من يعتمد الإلغاء (بلا أي بيانات أخرى) لنافذة نقطة البيع."""
        Users = self.env["res.users"].sudo()
        users = Users.search([
            ("hosny_pos_void_approver", "=", True),
            ("hosny_pos_void_password_hash", "!=", False),
            ("share", "=", False),
        ], order="name")
        if config_id:
            company = self.env["pos.config"].sudo().browse(config_id).company_id
            users = users.filtered(lambda u: company in u.company_ids)
        return [{"id": u.id, "name": u.name} for u in users]

    @api.model
    def hosny_approve_void(self, approver_id, password, details):
        """يفحص كلمة سر الإلغاء ويكتب السجل. لا يرفع استثناء للكاشير: يرجع رسالة."""
        details = details or {}
        reason = (details.get("reason") or "").strip()
        if not reason:
            return {"ok": False, "error": _("اكتب سبب الإلغاء أولاً.")}

        approver = self.env["res.users"].sudo().browse(int(approver_id or 0)).exists()
        if not approver or not approver.hosny_pos_void_approver or not approver.hosny_pos_void_password_hash:
            return {"ok": False, "error": _("هذا الحساب غير مفعّل لاعتماد الإلغاء.")}

        now = fields.Datetime.now()
        if approver.hosny_pos_void_locked_until and approver.hosny_pos_void_locked_until > now:
            minutes = max(1, int((approver.hosny_pos_void_locked_until - now).total_seconds() // 60) + 1)
            return {"ok": False, "error": _(
                "محاولات خاطئة كثيرة. الاعتماد بحساب %(name)s موقوف %(min)s دقيقة.",
                name=approver.name, min=minutes,
            )}

        valid = False
        try:
            valid = self.env["res.users"]._crypt_context().verify(
                password or "", approver.hosny_pos_void_password_hash
            )
        except ValueError:
            valid = False
        if not valid:
            failures = approver.hosny_pos_void_failures + 1
            vals = {"hosny_pos_void_failures": failures}
            if failures >= MAX_FAILURES:
                vals.update(hosny_pos_void_failures=0,
                            hosny_pos_void_locked_until=now + timedelta(minutes=LOCK_MINUTES))
            approver.write(vals)
            _logger.warning("POS void approval: wrong password for %s by uid %s (%s)",
                            approver.login, self.env.uid, failures)
            if failures >= MAX_FAILURES:
                return {"ok": False, "error": _(
                    "كلمة السر غير صحيحة. أُوقف الاعتماد بهذا الحساب %(min)s دقائق.", min=LOCK_MINUTES)}
            return {"ok": False, "error": _("كلمة السر غير صحيحة.")}

        approver.write({"hosny_pos_void_failures": 0, "hosny_pos_void_locked_until": False})

        config = self.env["pos.config"].sudo().browse(int(details.get("config_id") or 0)).exists()
        session = self.env["pos.session"].sudo().browse(int(details.get("session_id") or 0)).exists()
        order = self.env["pos.order"].sudo()
        if isinstance(details.get("order_id"), int):
            order = order.browse(details["order_id"]).exists()
        if not order and details.get("order_uuid"):
            order = order.search([("uuid", "=", details["order_uuid"])], limit=1)

        lines = details.get("lines") or []
        logs = self.sudo().browse()
        for line in lines:
            before = float(line.get("quantity_before") or 0.0)
            after = float(line.get("quantity_after") or 0.0)
            logs |= self.sudo().create({
                "action": "void_line",
                "reason": reason,
                "approved_by": approver.name,
                "approved_by_user_id": approver.id,
                "cashier": details.get("cashier") or self.env.user.name,
                "pos_session_id": session.id or False,
                "pos_config_id": config.id or session.config_id.id or False,
                "pos_order_id": order.id or False,
                "order_ref": details.get("order_ref") or order.pos_reference or order.name or "",
                "order_uuid": details.get("order_uuid") or "",
                "table_name": details.get("table") or "",
                "product_name": line.get("product") or "",
                "quantity_before": before,
                "quantity_after": after,
                "quantity_cancelled": before - after,
                "amount": float(line.get("amount") or 0.0),
                "notes": details.get("kind") == "order"
                and _("حذف الطلب كاملاً بعد إرساله") or "",
            })
        return {"ok": True, "approver": approver.name, "log_ids": logs.ids}

    @api.model
    def log_action(self, *args, **kwargs):
        # The POS user can no longer create audit rows directly (they would be
        # editable by the cashier); every row goes through here.
        return super(PosAuditLog, self.sudo()).log_action(*args, **kwargs).id


class PosOrder(models.Model):
    _inherit = "pos.order"

    # Integer only, no One2many: the POS reads every pos.order field (empty
    # _load_pos_data_fields), and a relation to a model the till does not load
    # is not worth the risk. Managers only — the cashier never needs it.
    hosny_void_count = fields.Integer(
        "الإلغاءات المعتمدة", compute="_compute_hosny_void_count", groups="point_of_sale.group_pos_manager"
    )

    def _compute_hosny_void_count(self):
        Log = self.env["pos.audit.log"].sudo()
        for order in self:
            order.hosny_void_count = Log.search_count(
                [("pos_order_id", "=", order.id), ("action", "=", "void_line")]
            ) if isinstance(order.id, int) else 0

    def action_hosny_void_logs(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("hosny_pos_controls.pos_audit_log_action")
        action["domain"] = [("pos_order_id", "=", self.id)]
        action["context"] = {"create": False}
        return action
