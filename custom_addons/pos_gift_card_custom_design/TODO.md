# TODO: Fix pos_gift_card_custom_design installation error

## Steps:
- [x] Analyze error and files (RPC_ERROR RelaxNG validation in gift_card_report.xml)
- [x] Plan: Fix invalid inherit_id on inner t-call in reports/gift_card_report.xml
- [x] Edit XML file
- [ ] Update module: ./odoo-bin -d odoo17_prod -u pos_gift_card_custom_design
- [ ] Test gift card printing in POS
- [ ] attempt_completion
