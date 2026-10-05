import logging


_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        UPDATE mrp_production
           SET pos_auto_mrp_generated = TRUE
         WHERE pos_order_id IS NOT NULL
            OR sale_order_id IS NOT NULL
            OR pos_order_line_id IS NOT NULL
            OR sale_order_line_id IS NOT NULL
        """
    )
    flagged = cr.rowcount
    cr.execute(
        """
        INSERT INTO pos_auto_mrp_production_pos_line_rel (production_id, pos_line_id)
        SELECT DISTINCT production_id, pos_line_id
          FROM (
                SELECT id AS production_id, pos_order_line_id AS pos_line_id
                  FROM mrp_production
                 WHERE pos_order_line_id IS NOT NULL
                UNION ALL
                SELECT mrp_production_id AS production_id, id AS pos_line_id
                  FROM pos_order_line
                 WHERE mrp_production_id IS NOT NULL
          ) legacy
        ON CONFLICT DO NOTHING
        """
    )
    linked = cr.rowcount
    _logger.info(
        "POS Auto MRP 19.0.5.0: marked %s existing linked MOs as automatic and migrated %s POS line links.",
        flagged,
        linked,
    )
