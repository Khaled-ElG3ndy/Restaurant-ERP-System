import logging


_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Disable the obsolete variant tab left by earlier module versions."""
    cr.execute(
        """
        UPDATE ir_ui_view
           SET active = FALSE
         WHERE id IN (
             SELECT res_id
               FROM ir_model_data
              WHERE module = 'hosny_purchase_packaging'
                AND name = 'product_product_form_purchase_packaging_templates'
                AND model = 'ir.ui.view'
         )
           AND active IS TRUE
        """
    )
    if cr.rowcount:
        _logger.info(
            "Hosny Purchase Packaging: disabled the obsolete product-variant purchase-packaging tab."
        )
