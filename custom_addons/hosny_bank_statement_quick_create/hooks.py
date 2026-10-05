from collections import Counter


def _normalized_name(record, language):
    return (record.with_context(lang=language).name or "").replace("ة", "ه").strip()


def post_init_hook(env):
    """Seed the branch on existing bank/cash journals from existing Hosny data."""
    journals = env["account.journal"].search([
        ("type", "in", ("bank", "cash")),
        ("analytic_account_id", "=", False),
    ])
    for journal in journals:
        accounts = env["account.analytic.account"].search([
            "|", ("company_id", "=", False), ("company_id", "=", journal.company_id.id)
        ])
        medina = accounts.filtered(
            lambda account: "مدينه" in _normalized_name(account, "ar_001")
            or "مدينه" in _normalized_name(account, "en_US")
        )[:1]
        jeddah = accounts.filtered(
            lambda account: "جده" in _normalized_name(account, "ar_001")
            or "جده" in _normalized_name(account, "en_US")
        )[:1]
        journal_name = " ".join((
            _normalized_name(journal, "ar_001"),
            _normalized_name(journal, "en_US"),
            _normalized_name(journal.default_account_id, "ar_001"),
            _normalized_name(journal.default_account_id, "en_US"),
        ))

        branch = env["account.analytic.account"]
        if "مدينه" in journal_name and medina:
            branch = medina
        elif "جده" in journal_name and jeddah:
            branch = jeddah
        else:
            history = env["account.move"].search([
                ("journal_id", "=", journal.id),
                ("analytic_account_id", "!=", False),
            ])
            counts = Counter(history.mapped("analytic_account_id").ids)
            if counts:
                branch = env["account.analytic.account"].browse(counts.most_common(1)[0][0])
            elif "عهده" in journal_name and jeddah:
                # These legacy employee-custody journals were created with the Jeddah cash journals.
                branch = jeddah
        if branch:
            journal.analytic_account_id = branch

