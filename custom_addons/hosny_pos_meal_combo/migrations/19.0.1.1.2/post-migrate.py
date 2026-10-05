import logging

from odoo import SUPERUSER_ID, api


_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Backfill bundle-cost attribution without touching product costs/valuation."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    parents = env["pos.order.line"].search([
        ("is_additional_final_parent", "=", True),
    ])
    if parents:
        bundle_lines = parents | parents.mapped("order_id.lines").filtered(
            "is_additional_final_product"
        )
        # Preserve the cost that core POS had already computed for records whose
        # secondary MO has not completed yet.  Actual completed MOs replace this
        # fallback during the refresh below.
        for line in bundle_lines:
            line.write({"mrp_direct_cost": line.total_cost})
        parents._additional_final_refresh_bundle_costs()

    # Recreate the SQL view so report.pos.order uses the inherited bundle-margin
    # expression immediately after this module upgrade.
    env["report.pos.order"].init()
    _logger.info(
        "Hosny POS Meal Combo: backfilled manufacturing-cost allocation for %s additional-product parent lines.",
        len(parents),
    )
