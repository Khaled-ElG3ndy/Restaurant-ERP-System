{
    "name": "Hosny Purchase Return Automation",
    "version": "19.0.1.0.0",
    "category": "Purchases",
    "summary": "Create vendor bills, vendor credit notes, and stock returns from purchase orders",
    "author": "Hosny",
    "license": "LGPL-3",
    "depends": [
        "purchase_stock",
        "hosny_account_analytic_header",
        "hosny_purchase_requisition_name",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/purchase_order_views.xml",
        "views/stock_picking_views.xml",
        "wizard/purchase_vendor_bill_confirm_views.xml",
        "wizard/purchase_return_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
