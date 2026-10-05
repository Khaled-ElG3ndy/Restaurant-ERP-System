from collections import Counter

from odoo.exceptions import UserError


def post_init_hook(env):
    agreements = env["purchase.requisition"].search([("reference", "!=", False)])
    names = [agreement.reference.strip() for agreement in agreements if agreement.reference and agreement.reference.strip()]
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicates:
        raise UserError("Duplicate purchase agreement names found: %s" % ", ".join(duplicates))
    for agreement in agreements:
        if agreement.reference and agreement.reference.strip():
            agreement.with_context(skip_hosny_agreement_name_sync=True).name = agreement.reference.strip()
