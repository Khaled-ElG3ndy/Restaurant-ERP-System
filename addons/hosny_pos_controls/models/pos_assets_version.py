import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

POS_BUNDLES = ("point_of_sale.assets_prod", "point_of_sale.assets_prod_dark")


class PosConfig(models.Model):
    _inherit = "pos.config"

    @api.model
    def hosny_pos_assets_links(self, bundle, rtl, loaded=None):
        """روابط حزمة نقطة البيع الحالية على السيرفر، بنفس ما تضعه صفحة /pos/ui.

        الشاشة تقارنها بما حمّلته لتعرف أن هناك نسخة أحدث (static/src/js/auto_update.js).
        الروابط من ذاكرة أودو المؤقتة للحزم، فلا بناء ولا قراءة ملفات في كل سؤال.
        """
        if bundle not in POS_BUNDLES:
            bundle = POS_BUNDLES[0]
        links = self.env["ir.qweb"]._generate_asset_links_cache(
            bundle,
            css=True,
            js=True,
            assets_params=self.env["ir.asset"]._get_asset_params(),
            rtl=bool(rtl),
        )
        links = [link for link in links if isinstance(link, str) and link.startswith("/web/assets/")]
        if loaded and set(loaded) - set(links):
            _logger.info(
                "Hosny POS outdated on this screen: user %s has %s, server %s",
                self.env.uid, sorted(loaded), links,
            )
        return links
