import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """تهيئة يومية الرواتب والحسابات الافتراضية لكل شركة عليها محاسبة مفعّلة."""
    companies = env["res.company"].search([("chart_template", "!=", False)])
    if not companies:
        companies = env["res.company"].search([])
    for company in companies:
        try:
            company._hosny_setup_payroll_accounting()
        except Exception:  # pragma: no cover - التهيئة لا يجب أن تُفشل التثبيت
            _logger.exception(
                "hosny_payroll_account: تعذّرت التهيئة التلقائية للشركة %s",
                company.display_name,
            )
