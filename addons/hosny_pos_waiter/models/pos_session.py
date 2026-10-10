from odoo import _, api, models
from odoo.exceptions import UserError

WAITER_NO_SHIFT = "حساب المتر لا يفتح الوردية ولا يغلقها، ولا يعمل إيداع / سحب — هذا من الكاشير."


def _waiter_blocked(method_name):
    def method(self, *args, **kwargs):
        if self.env.user._hosny_is_pos_waiter():
            raise UserError(_(WAITER_NO_SHIFT))
        return getattr(super(PosSession, self), method_name)(*args, **kwargs)

    method.__name__ = method_name
    return method


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user._hosny_is_pos_waiter():
            raise UserError(_(WAITER_NO_SHIFT))
        return super().create(vals_list)

    set_opening_control = _waiter_blocked("set_opening_control")
    try_cash_in_out = _waiter_blocked("try_cash_in_out")
    post_closing_cash_details = _waiter_blocked("post_closing_cash_details")
    update_closing_control_state_session = _waiter_blocked("update_closing_control_state_session")
    close_session_from_ui = _waiter_blocked("close_session_from_ui")
    action_pos_session_closing_control = _waiter_blocked("action_pos_session_closing_control")
    action_pos_session_validate = _waiter_blocked("action_pos_session_validate")
    action_pos_session_close = _waiter_blocked("action_pos_session_close")
