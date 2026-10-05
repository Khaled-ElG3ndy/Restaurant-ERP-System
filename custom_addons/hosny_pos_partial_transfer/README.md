# Hosny POS Partial Transfer

`hosny_pos_partial_transfer` adds a production-ready Partial Transfer flow to Odoo 17 Restaurant POS.

## What it does

- Adds a new `Partial Transfer` button next to the restaurant control buttons.
- Opens a modern OWL popup that lists the current order lines.
- Lets the cashier choose how much of each line to move.
- Lets the cashier choose a real restaurant destination table.
- Transfers only the selected quantities.
- Merges into the active destination order when one exists.
- Creates a new destination order when the table is empty.
- Preserves unit price, discount, notes, attributes, taxes, and combo relationships.
- Keeps the original Odoo `Transfer` button untouched.

## Functional notes

- Combo lines move together to preserve combo structure.
- Source lines are reduced correctly.
- Fully moved source lines are removed when quantity changes are allowed.
- When kitchen/preparation mode prevents direct quantity reduction, the module follows Odoo's draft-adjustment pattern instead of forcing an unsafe direct rewrite.
- Restaurant table counters are refreshed locally after transfer.

## Installation

1. Make sure `custom_addons` is in your Odoo addons path.
2. Restart Odoo.
3. Upgrade the module list if needed.
4. Install `Hosny POS Partial Transfer` from Apps, or upgrade it from command line.

## CLI upgrade

```bash
/opt/odoo17-venv/bin/python /opt/odoo17-source/odoo-bin -c /etc/odoo17.conf -d odoo17_prod -u hosny_pos_partial_transfer --stop-after-init
```

## Service restart

```bash
systemctl restart odoo17
```

## Debug and test checklist

1. Open a restaurant session.
2. Open a table with multiple products.
3. Click `Partial Transfer`.
4. Move one full line to an empty table.
5. Move a partial quantity from a grouped product line.
6. Move items to a table that already has an active order and verify merge.
7. Verify notes, attributes, combo lines, and prices are preserved.
8. Send kitchen changes before and after transfer and confirm no broken preparation flow.
9. Open the destination table from another POS tab or session and confirm draft sync.

