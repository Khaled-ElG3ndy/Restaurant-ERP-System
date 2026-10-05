import json

from odoo import SUPERUSER_ID, api, models


DEFERRED_PAYMENT_NAME_AR = "أجل"
DEFERRED_PAYMENT_NAME_EN = "Deferred"


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    @api.model
    def _hosny_ensure_advance_payment_method(self):
        """Keep one customer deferred payment method ready for every POS branch."""
        PosConfig = self.env["pos.config"].sudo()
        configs = PosConfig.search([])

        for config in configs:
            payment_method = self._hosny_get_or_create_advance_payment_method(config)
            self._hosny_force_advance_payment_method_values(payment_method)
            self._hosny_link_advance_payment_method_to_configs(payment_method, config)

        self.env.invalidate_all()
        return True

    @api.model
    def _hosny_get_or_create_advance_payment_method(self, config):
        company = config.company_id
        PaymentMethod = self.sudo().with_company(company)
        linked_pay_later = config.payment_method_ids.filtered(
            lambda method: not method.journal_id and method.company_id == company
        ).sorted(lambda method: (method.sequence, method.id))[:1]
        if linked_pay_later:
            return linked_pay_later

        unlinked_pay_later = PaymentMethod.search(
            [
                ("journal_id", "=", False),
                ("company_id", "=", company.id),
                ("config_ids", "=", False),
            ],
            order="sequence, id",
            limit=1,
        )
        if unlinked_pay_later:
            return unlinked_pay_later

        return PaymentMethod.create(
            {
                "name": DEFERRED_PAYMENT_NAME_AR,
                "company_id": company.id,
                "journal_id": False,
                "split_transactions": True,
                "sequence": 3,
                "payment_method_type": "none",
            }
        )

    def _hosny_force_advance_payment_method_values(self, payment_method):
        receivable_account = self._hosny_find_deferred_receivable_account(payment_method.company_id)
        translated_name = json.dumps(
            {
                "en_US": DEFERRED_PAYMENT_NAME_EN,
                "ar_001": DEFERRED_PAYMENT_NAME_AR,
            },
            ensure_ascii=False,
        )
        self.env.cr.execute(
            """
                UPDATE pos_payment_method
                   SET name = COALESCE(name, '{}'::jsonb) || %s::jsonb,
                       journal_id = NULL,
                       outstanding_account_id = NULL,
                       split_transactions = TRUE,
                       active = TRUE,
                       sequence = 3,
                       payment_method_type = 'none',
                       receivable_account_id = COALESCE(%s, receivable_account_id),
                       write_uid = %s,
                       write_date = NOW()
                 WHERE id = %s
            """,
            [translated_name, receivable_account.id or None, SUPERUSER_ID, payment_method.id],
        )

    def _hosny_find_deferred_receivable_account(self, company):
        if company.account_default_pos_receivable_account_id:
            return company.account_default_pos_receivable_account_id

        Account = self.env["account.account"].sudo().with_company(company)
        receivable_domain = [
            ("account_type", "=", "asset_receivable"),
            ("reconcile", "=", True),
        ]
        accounts = Account.search(
            [
                *receivable_domain,
                "|",
                ("name", "ilike", "عملاء محليون"),
                ("code", "=", "141401"),
            ]
        )
        company_accounts = accounts.filtered(lambda account: company in account.company_ids)
        return (
            company_accounts[:1]
            or accounts.filtered(lambda account: not account.company_ids)[:1]
            or accounts[:1]
            or Account.search(receivable_domain, limit=1)
        )

    def _hosny_link_advance_payment_method_to_configs(self, payment_method, configs):
        config_ids = configs.ids
        self.env.cr.execute(
            """
                DELETE FROM pos_config_pos_payment_method_rel rel
                      USING pos_payment_method pm
                     WHERE rel.pos_payment_method_id = pm.id
                       AND rel.pos_config_id = ANY(%s)
                       AND rel.pos_payment_method_id != %s
                       AND pm.journal_id IS NULL
            """,
            [config_ids, payment_method.id],
        )
        self.env.cr.execute(
            """
                INSERT INTO pos_config_pos_payment_method_rel
                            (pos_config_id, pos_payment_method_id)
                     SELECT id, %s
                       FROM pos_config
                      WHERE id = ANY(%s)
                ON CONFLICT DO NOTHING
            """,
            [payment_method.id, config_ids],
        )
        self.env.cr.execute(
            """
                UPDATE pos_config
                   SET write_uid = %s,
                       write_date = NOW(),
                       last_data_change = NOW()
                 WHERE id = ANY(%s)
            """,
            [SUPERUSER_ID, config_ids],
        )
