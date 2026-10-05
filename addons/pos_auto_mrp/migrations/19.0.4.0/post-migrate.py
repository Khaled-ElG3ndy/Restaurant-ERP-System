import logging

from odoo import SUPERUSER_ID, api


_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    profiles = env["pos.mrp.source.profile"]._sync_profiles_from_leaf_locations()

    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = 'product_template'
           AND column_name = 'preferred_mrp_source_location_id'
        """
    )
    if not cr.fetchone():
        return

    cr.execute(
        """
        SELECT id, preferred_mrp_source_location_id
          FROM product_template
         WHERE preferred_mrp_source_location_id IS NOT NULL
        """
    )
    migrated = 0
    unresolved = []
    for product_id, location_id in cr.fetchall():
        profile = profiles.filtered(
            lambda item: location_id in item.route_ids.mapped("location_id").ids
        )[:1]
        if profile:
            env["product.template"].browse(product_id).write({
                "pos_mrp_source_profile_id": profile.id,
            })
            migrated += 1
        else:
            unresolved.append((product_id, location_id))

    if unresolved:
        _logger.warning(
            "POS Auto MRP: %s legacy product source values had no complete per-POS route and were left unset: %s",
            len(unresolved),
            unresolved,
        )

    cr.execute(
        "ALTER TABLE product_template DROP COLUMN IF EXISTS preferred_mrp_source_location_id CASCADE"
    )
    _logger.info(
        "POS Auto MRP: created/synchronized %s logical source profiles and migrated %s products; legacy field removed.",
        len(profiles),
        migrated,
    )
