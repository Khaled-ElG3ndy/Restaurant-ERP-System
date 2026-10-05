import base64
import json
from urllib.parse import quote

from dateutil.relativedelta import relativedelta
from markupsafe import Markup
from reportlab.graphics.barcode import createBarcodeDrawing

from odoo import api, fields, models
from odoo.tools.image import image_data_uri, image_process
from odoo.tools.misc import file_path

from . import coupon_design

# The coupon embeds its own webfont so the printed card is identical on every
# server, whatever fonts happen to be installed there.  Reading and encoding the
# four weights is worth caching - they never change at runtime.
_FONT_WEIGHTS = (400, 600, 700, 900)
_FONT_FAMILY = "HosnyCoupon"
# Fallbacks only matter if the embedded face somehow fails to load.
_FONT_STACK = "HosnyCoupon, Cairo, Tahoma, sans-serif"
_font_css_cache = None


class LoyaltyCard(models.Model):
    _inherit = "loyalty.card"

    def _hosny_gc_datetime_label(self, value):
        self.ensure_one()
        if not value:
            return ""
        if not hasattr(value, "hour"):
            value = fields.Datetime.to_datetime(value)
        localized = fields.Datetime.context_timestamp(self, value)
        months = {
            1: "يناير",
            2: "فبراير",
            3: "مارس",
            4: "أبريل",
            5: "مايو",
            6: "يونيو",
            7: "يوليو",
            8: "أغسطس",
            9: "سبتمبر",
            10: "أكتوبر",
            11: "نوفمبر",
            12: "ديسمبر",
        }
        suffix = "ص" if localized.hour < 12 else "م"
        hour = localized.hour % 12 or 12
        return "%02d:%02d %s - %s %s %s" % (
            hour,
            localized.minute,
            suffix,
            localized.day,
            months[localized.month],
            localized.year,
        )

    def _hosny_gc_date_label(self, value):
        self.ensure_one()
        if not value:
            return ""
        value = fields.Date.to_date(value)
        months = {
            1: "يناير",
            2: "فبراير",
            3: "مارس",
            4: "أبريل",
            5: "مايو",
            6: "يونيو",
            7: "يوليو",
            8: "أغسطس",
            9: "سبتمبر",
            10: "أكتوبر",
            11: "نوفمبر",
            12: "ديسمبر",
        }
        return "%s %s %s" % (value.day, months[value.month], value.year)

    def _hosny_gc_expiry_label(self):
        self.ensure_one()
        expiry = self.expiration_date
        if not expiry and self.create_date:
            expiry = fields.Datetime.to_datetime(self.create_date) + relativedelta(months=4)
        return self._hosny_gc_date_label(expiry) if expiry else "حسب سياسة القسيمة"

    def _hosny_gc_currency_label(self):
        self.ensure_one()
        if self.currency_id.name == "SAR":
            return "ريال سعودي"
        return self.currency_id.full_name or self.currency_id.name

    def _hosny_gc_amount_label(self):
        self.ensure_one()
        amount = self.currency_id.round(self.points)
        return "%s %s" % (("{:,.2f}".format(amount)), self._hosny_gc_currency_label())

    def _hosny_gc_amount_number_label(self):
        self.ensure_one()
        return "{:,.2f}".format(self.currency_id.round(self.points))

    def _hosny_gc_currency_short_label(self):
        self.ensure_one()
        if self.currency_id.name == "SAR":
            return "ريال"
        return self.currency_id.name

    def _hosny_gc_amount_words_label(self):
        self.ensure_one()
        amount = abs(self.currency_id.round(self.points))
        integer = int(amount)
        cents = int(round((amount - integer) * 100))
        words = self._hosny_gc_number_to_arabic(integer) or str(integer)
        label = "%s %s" % (words, self._hosny_gc_currency_label())
        if cents:
            label += " و %s هللة" % (self._hosny_gc_number_to_arabic(cents) or str(cents))
        return label

    def _hosny_gc_barcode_src(self, barcode_type="Code128", width=620, height=90):
        self.ensure_one()
        if not self.code:
            return False
        try:
            drawing = createBarcodeDrawing(
                barcode_type,
                value=self.code,
                width=int(width),
                height=int(height),
            )
            png = drawing.asString("png")
        except Exception:
            return False
        return "data:image/png;base64,%s" % base64.b64encode(png).decode("ascii")

    def _hosny_gc_logo_src(self):
        self.ensure_one()
        # Prefer the full-size logo: logo_web is a 180px thumbnail, which comes
        # out soft at the ~18mm the coupon prints it at. 256px keeps the mark
        # comfortably above 300 DPI without inflating a batch of coupons.
        logo = self.company_id.logo or self.company_id.logo_web
        if not logo:
            return False
        resized = image_process(base64.b64decode(logo), size=(256, 256))
        return image_data_uri(base64.b64encode(resized))

    def _hosny_gc_expiry_numeric_label(self):
        self.ensure_one()
        expiry = self.expiration_date
        if not expiry and self.create_date:
            expiry = fields.Datetime.to_datetime(self.create_date) + relativedelta(months=4)
        if not expiry:
            return ""
        expiry = fields.Date.to_date(expiry)
        return "%02d / %02d / %s" % (expiry.day, expiry.month, expiry.year)

    def _hosny_gc_font_css(self):
        """@font-face block embedding the coupon webfont as data URIs."""
        global _font_css_cache
        if _font_css_cache is None:
            faces = []
            for weight in _FONT_WEIGHTS:
                path = file_path(
                    "pos_gift_card_custom_design/static/fonts/Cairo-%s.ttf" % weight
                )
                with open(path, "rb") as fh:
                    payload = base64.b64encode(fh.read()).decode("ascii")
                faces.append(
                    "@font-face{font-family:'%s';font-style:normal;font-weight:%s;"
                    "src:url(data:font/truetype;charset=utf-8;base64,%s) "
                    "format('truetype');}" % (_FONT_FAMILY, weight, payload)
                )
            _font_css_cache = "".join(faces)
        return _font_css_cache

    def _hosny_gc_branch_labels(self):
        """Branch names for the footer, read live from the company tree.

        Branches are the child companies of the brand, so opening or closing
        one is reflected on the next printed coupon with no edit here. sudo is
        needed because a cashier is normally restricted to their own company.
        """
        self.ensure_one()
        company = self.company_id or self.env.company
        root = company.parent_id or company
        companies = self.env["res.company"].sudo().search(
            [("id", "child_of", root.id)], order="sequence, id"
        )
        branches = companies - root
        if not branches:
            # Single-company setup: fall back to the brand's own location.
            partner = root.partner_id
            location = ", ".join(p for p in (partner.city, partner.street) if p)
            return [location] if location else []
        labels = []
        for branch in branches:
            label = branch.partner_id.city
            if not label:
                # "مطعم حسني - جدة" reads better as just "جدة" next to the brand.
                label = branch.name or ""
                if root.name and label.startswith(root.name):
                    label = label[len(root.name):].strip(" -–—") or branch.name
            labels.append(label)
        return labels

    def _hosny_gc_coupon_values(self):
        """Everything the artwork needs, resolved from the card and company."""
        self.ensure_one()
        company = self.company_id or self.env.company
        phones = [
            part.strip()
            for part in (company.phone or "0544260006 | 0501037766 | 0588003300")
            .replace("/", "|").split("|")
            if part.strip()
        ]
        return {
            "brand": company.name or "مطعم حسني",
            "tagline": "تجربة طعام لا تُنسى",
            "headline": "قسيمة خصم",
            "subtitle": "استمتع بمذاقنا ووفر أكثر",
            "value_label": "قيمة القسيمة",
            "amount": self._hosny_gc_amount_number_label(),
            "currency": self._hosny_gc_currency_short_label(),
            "expiry": self._hosny_gc_expiry_numeric_label(),
            "expiry_label": "صالحة حتى",
            "code": self.code or "-",
            "code_title": "كود القسيمة",
            "code_hint_1": "يُقدّم للكاشير",
            "code_hint_2": "قبل إتمام العملية",
            "branches_label": "فروعنا",
            "branches": self._hosny_gc_branch_labels(),
            "phones": phones,
            "email": company.email or "hosnyrily@yahoo.com",
            "logo_src": self._hosny_gc_logo_src(),
            "barcode_src": self._hosny_gc_barcode_src("Code128", 960, 210),
            "font_family": _FONT_STACK,
        }

    def _hosny_gc_card_svg(self):
        """The coupon artwork, ready to drop straight into a QWeb template."""
        self.ensure_one()
        return Markup(coupon_design.build_card_svg(**self._hosny_gc_coupon_values()))

    def _hosny_gc_card_svg_src(self):
        """Data URI for mail/chatter previews using the same dynamic artwork."""
        self.ensure_one()
        svg = str(self._hosny_gc_card_svg())
        font_css = self._hosny_gc_font_css()
        svg = svg.replace(
            "<defs>",
            '<defs><style type="text/css"><![CDATA[%s]]></style>' % font_css,
            1,
        )
        payload = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        return "data:image/svg+xml;base64,%s" % payload

    def _hosny_gc_card_svg_path(self):
        self.ensure_one()
        return "/hosny/gift-card/%s/%s/svg" % (self.id, quote(self.code or "-"))

    def _hosny_gc_preview_path(self):
        self.ensure_one()
        return "/hosny/gift-card/%s/%s/preview" % (self.id, quote(self.code or "-"))

    def _hosny_gc_download_path(self):
        self.ensure_one()
        return "/hosny/gift-card/%s/%s/download" % (self.id, quote(self.code or "-"))

    def action_hosny_preview_gift_card(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": self._hosny_gc_preview_path(),
            "target": "new",
        }

    def action_hosny_download_gift_card(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": self._hosny_gc_download_path(),
            "target": "self",
        }

    def _hosny_gc_number_to_arabic(self, number):
        ones = {
            0: "صفر",
            1: "واحد",
            2: "اثنان",
            3: "ثلاثة",
            4: "أربعة",
            5: "خمسة",
            6: "ستة",
            7: "سبعة",
            8: "ثمانية",
            9: "تسعة",
            10: "عشرة",
            11: "أحد عشر",
            12: "اثنا عشر",
            13: "ثلاثة عشر",
            14: "أربعة عشر",
            15: "خمسة عشر",
            16: "ستة عشر",
            17: "سبعة عشر",
            18: "ثمانية عشر",
            19: "تسعة عشر",
        }
        tens = {
            20: "عشرون",
            30: "ثلاثون",
            40: "أربعون",
            50: "خمسون",
            60: "ستون",
            70: "سبعون",
            80: "ثمانون",
            90: "تسعون",
        }
        hundreds = {
            100: "مائة",
            200: "مائتان",
            300: "ثلاثمائة",
            400: "أربعمائة",
            500: "خمسمائة",
            600: "ستمائة",
            700: "سبعمائة",
            800: "ثمانمائة",
            900: "تسعمائة",
        }

        number = int(number)
        if number < 20:
            return ones.get(number, "")
        if number < 100:
            ten = number // 10 * 10
            one = number % 10
            return tens[ten] if not one else "%s و %s" % (ones[one], tens[ten])
        if number < 1000:
            hundred = number // 100 * 100
            rest = number % 100
            return hundreds[hundred] if not rest else "%s و %s" % (
                hundreds[hundred],
                self._hosny_gc_number_to_arabic(rest),
            )
        if number < 1000000:
            thousand = number // 1000
            rest = number % 1000
            if thousand == 1:
                prefix = "ألف"
            elif thousand == 2:
                prefix = "ألفان"
            elif 3 <= thousand <= 10:
                prefix = "%s آلاف" % self._hosny_gc_number_to_arabic(thousand)
            else:
                prefix = "%s ألف" % self._hosny_gc_number_to_arabic(thousand)
            return prefix if not rest else "%s و %s" % (
                prefix,
                self._hosny_gc_number_to_arabic(rest),
            )
        return ""


class LoyaltyProgram(models.Model):
    _inherit = "loyalty.program"

    @api.model
    def _hosny_apply_discount_coupon_labels(self):
        label = "كوبونات الخصم"
        programs = self.search([("program_type", "=", "gift_card")])
        if programs:
            programs.write({"name": label})
        products = programs.rule_ids.product_ids
        products |= self.env["product.product"].with_context(active_test=False).search([
            ("name", "=", "Gift Card"),
        ])
        templates = products.product_tmpl_id
        if templates:
            templates.with_context(lang=None).write({"name": label})
        if products:
            self.env["sale.order.line"].search([
                ("product_id", "in", products.ids),
                ("name", "in", ["Gift Card", "Gift Card\n"]),
            ]).write({"name": label})
        return True


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_view_gift_cards(self):
        action = super().action_view_gift_cards()
        action["name"] = "كوبونات الخصم"
        return action
