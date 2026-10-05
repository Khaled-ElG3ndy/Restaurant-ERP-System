from odoo import http
from odoo.http import content_disposition, request


class HosnyGiftCardController(http.Controller):
    def _get_card(self, card_id, code):
        return (
            request.env["loyalty.card"]
            .sudo()
            .search([("id", "=", card_id), ("code", "=", code)], limit=1)
        )

    @http.route(
        "/hosny/gift-card/<int:card_id>/<string:code>/svg",
        type="http",
        auth="public",
        website=True,
        readonly=True,
    )
    def gift_card_svg(self, card_id, code, **kwargs):
        card = self._get_card(card_id, code)
        if not card:
            return request.not_found()
        svg = str(card._hosny_gc_card_svg())
        svg = svg.replace(
            "<defs>",
            '<defs><style type="text/css"><![CDATA[%s]]></style>'
            % card._hosny_gc_font_css(),
            1,
        )
        return request.make_response(
            svg.encode("utf-8"),
            headers=[
                ("Content-Type", "image/svg+xml; charset=utf-8"),
                ("Cache-Control", "private, max-age=300"),
            ],
        )

    @http.route(
        "/hosny/gift-card/<int:card_id>/<string:code>/preview",
        type="http",
        auth="public",
        website=True,
        readonly=True,
    )
    def preview_gift_card(self, card_id, code, **kwargs):
        card = self._get_card(card_id, code)
        if not card:
            return request.not_found()
        image_url = card._hosny_gc_card_svg_path()
        download_url = card._hosny_gc_download_path()
        html = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>معاينة القسيمة</title>
  <style>
    * { box-sizing: border-box; }
    html, body {
      min-height: 100%%;
      margin: 0;
      padding: 0;
      background: #e9dec6;
      color: #2b210f;
      font-family: Tahoma, Arial, sans-serif;
    }
    body {
      display: grid;
      place-items: center;
      min-height: 100vh;
      padding: 28px;
    }
    .preview-wrap {
      width: min(96vw, 1489px);
      display: grid;
      gap: 16px;
      justify-items: center;
    }
    .coupon-frame {
      width: 100%%;
      border-radius: 18px;
      box-shadow: 0 18px 46px rgba(43, 33, 15, 0.18);
      overflow: hidden;
    }
    .coupon-frame img {
      display: block;
      width: 100%%;
      height: auto;
      border: 0;
    }
    .preview-actions {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 10px;
    }
    .preview-actions a,
    .preview-actions button {
      min-width: 118px;
      padding: 10px 26px;
      border: 2px solid #b79a5a;
      border-radius: 999px;
      background: #453824;
      color: #fff;
      cursor: pointer;
      font: 900 15px/1.2 Tahoma, Arial, sans-serif;
      text-align: center;
      text-decoration: none;
    }
    .preview-actions button {
      background: #f3eadb;
      color: #453824;
    }
    @media print {
      body { display: block; padding: 0; background: #fff; }
      .preview-wrap, .coupon-frame { width: 148mm; box-shadow: none; border-radius: 0; }
      .preview-actions { display: none; }
    }
  </style>
</head>
<body>
  <main class="preview-wrap">
    <div class="coupon-frame">
      <img src="%s" alt="قسيمة الخصم"/>
    </div>
    <div class="preview-actions">
      <a href="%s">تحميل</a>
      <button type="button" onclick="window.close()">إغلاق</button>
    </div>
  </main>
</body>
</html>""" % (image_url, download_url)
        return request.make_response(
            html,
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )

    @http.route(
        "/hosny/gift-card/<int:card_id>/<string:code>/download",
        type="http",
        auth="public",
        website=True,
        readonly=True,
    )
    def download_gift_card(self, card_id, code, **kwargs):
        card = self._get_card(card_id, code)
        if not card:
            return request.not_found()
        pdf = request.env["ir.actions.report"].sudo()._render_qweb_pdf(
            "loyalty.gift_card_report_i18n",
            [card.id],
        )[0]
        filename = "gift-card-%s.pdf" % (card.code or card.id)
        return request.make_response(
            pdf,
            headers=[
                ("Content-Type", "application/pdf"),
                ("Content-Length", len(pdf)),
                ("Content-Disposition", content_disposition(filename)),
            ],
        )
