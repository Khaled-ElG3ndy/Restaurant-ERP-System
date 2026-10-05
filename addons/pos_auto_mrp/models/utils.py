from odoo.exceptions import UserError


def boolean_search_domain(record_ids, operator, value):
    """Return an id domain for a computed Boolean on Odoo's normalized operators."""
    if operator in ("=", "=="):
        matches = lambda candidate: candidate == bool(value)
    elif operator == "!=":
        matches = lambda candidate: candidate != bool(value)
    elif operator in ("in", "not in"):
        values = (
            list(value)
            if hasattr(value, "__iter__") and not isinstance(value, (str, bytes, bool))
            else [value]
        )
        matches = lambda candidate: (candidate in values) == (operator == "in")
    else:
        raise UserError("Unsupported Boolean search operator: %s" % operator)

    true_matches = matches(True)
    false_matches = matches(False)
    if true_matches and false_matches:
        return []
    if not true_matches and not false_matches:
        return [("id", "=", 0)]
    return [("id", "in" if true_matches else "not in", record_ids)]
