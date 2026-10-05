from odoo import api, SUPERUSER_ID

from odoo.addons.hosny_hr_work_location.hooks import (
    _backfill_historical_snapshots,
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _backfill_historical_snapshots(env)
