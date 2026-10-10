from markupsafe import escape

from odoo import http
from odoo.http import request

from odoo.addons.point_of_sale.controllers.main import PosController

WAITER_PAGE = """<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>نقطة البيع</title>
<style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#f4f6f9;font-family:Cairo,Tahoma,sans-serif;color:#1f2a44}
.box{max-width:440px;margin:16px;padding:28px 24px;background:#fff;border-radius:14px;
box-shadow:0 6px 24px rgba(0,0,0,.08);text-align:center}
h1{font-size:20px;margin:0 0 12px}p{font-size:16px;line-height:1.7;margin:0 0 20px}
a{display:inline-block;padding:10px 22px;border-radius:10px;background:#1f3a6e;color:#fff;text-decoration:none}
</style></head><body><div class="box">
<h1>%(title)s</h1><p>%(body)s</p><a href="%(href)s">%(link)s</a>
</div></body></html>"""


class HosnyWaiterPosController(PosController):

    @http.route()
    def pos_web(self, config_id=False, from_backend=False, subpath=None, **k):
        blocked = self._hosny_waiter_block(config_id)
        if blocked:
            return blocked
        return super().pos_web(config_id=config_id, from_backend=from_backend, subpath=subpath, **k)

    def _hosny_waiter_block(self, config_id):
        user = request.env.user
        if not user._is_internal() or not config_id or not str(config_id).isdigit():
            return None
        config_id = int(config_id)
        # أودو يقرأ نقطة البيع بـ sudo: المقيّد بفرع كان يفتح أي فرع من الرابط
        if user._hosny_is_branch_cashier() and config_id not in user.sudo().pos_config_ids.ids:
            return request.redirect("/odoo/action-point_of_sale.action_client_pos_menu")
        if not user._hosny_is_pos_waiter():
            return None
        session = request.env["pos.session"].sudo().search([
            ("config_id", "=", config_id),
            ("state", "=", "opened"),
            ("rescue", "=", False),
        ], limit=1)
        if session:
            return None
        html = WAITER_PAGE % {
            "title": escape("الوردية غير مفتوحة"),
            "body": escape("لا توجد وردية مفتوحة في هذا الفرع الآن. اطلب من الكاشير فتح الوردية، ثم أعد المحاولة."),
            "href": escape("/pos/ui/%s" % config_id),
            "link": escape("إعادة المحاولة"),
        }
        return request.make_response(html, headers=[
            ("Content-Type", "text/html; charset=utf-8"),
            ("Cache-Control", "no-store"),
        ])
