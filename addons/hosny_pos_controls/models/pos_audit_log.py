from odoo import models, fields, api

class PosAuditLog(models.Model):
    _name = 'pos.audit.log'
    _description = 'POS Audit Log'
    _order = 'create_date desc'
    _rec_name = 'action'

    action = fields.Selection([
        ('discount',    'Discount Applied'),
        ('refund',      'Refund'),
        ('void',        'Order Void/Cancel'),
        ('price_edit',  'Price Edit'),
        ('cash_in',     'Cash In'),
        ('cash_out',    'Cash Out'),
        ('session_open','Session Open'),
        ('session_close','Session Close'),
    ], string='Action', required=True)

    reason = fields.Char('Reason', required=True)
    approved_by = fields.Char('Approved By (PIN User)', required=True)
    cashier = fields.Char('Cashier')
    pos_session_id = fields.Many2one('pos.session', 'POS Session')
    pos_order_id = fields.Many2one('pos.order', 'POS Order')
    amount = fields.Float('Amount/Value', digits=(10, 2))
    notes = fields.Text('Notes')

    @api.model
    def log_action(self, action, reason, approved_by, cashier=None,
                   session_id=None, order_id=None, amount=0.0, notes=None):
        return self.create({
            'action': action,
            'reason': reason,
            'approved_by': approved_by,
            'cashier': cashier or '',
            'pos_session_id': session_id,
            'pos_order_id': order_id,
            'amount': amount,
            'notes': notes or '',
        })
