from . import models


def post_init_hook(env):
    """يولّد أسطر أنواع الفواتير للطابعات الموجودة قبل تثبيت الموديول."""
    env["pos.printer"].search([])._ensure_lines()
