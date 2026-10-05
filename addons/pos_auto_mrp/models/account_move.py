# -*- coding: utf-8 -*-

import logging

from odoo import _, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_set_to_draft_bulk(self):
        """Reset selected posted entries to draft without aborting the whole batch."""
        # Only process general journal entries (move_type='entry')
        entries = self.filtered(lambda m: m.move_type == 'entry')
        
        reset_count = 0
        skipped_count = 0
        failed_moves = []

        for move in entries:
            if move.state != "posted":
                skipped_count += 1
                continue

            try:
                with self.env.cr.savepoint():
                    move.button_draft()
                reset_count += 1
            except (AccessError, UserError, ValidationError) as exc:
                failed_moves.append(_("%(move)s: %(error)s", move=move.display_name, error=exc))
                _logger.info(
                    "Bulk reset to draft skipped for journal entry %s (%s): %s",
                    move.display_name,
                    move.id,
                    exc,
                )
            except Exception:
                failed_moves.append(_("%s: unexpected error", move.display_name))
                _logger.exception(
                    "Unexpected error during bulk reset to draft for journal entry %s (%s)",
                    move.display_name,
                    move.id,
                )
        
        # Count records that were skipped due to wrong move_type
        wrong_type_count = len(self) - len(entries)

        message_parts = []
        if reset_count:
            message_parts.append(_("%s journal entries were reset to draft.", reset_count))
        if skipped_count:
            message_parts.append(_("%s selected entries were skipped because they were not posted.", skipped_count))
        if wrong_type_count:
            message_parts.append(_("%s selected records were skipped because they are not journal entries.", wrong_type_count))
        if failed_moves:
            message_parts.append(_("%s journal entries could not be reset.", len(failed_moves)))
            message_parts.extend(failed_moves[:5])
        if not message_parts:
            message_parts.append(_("No journal entries were updated."))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Set to Draft (Bulk)"),
                "message": "\n".join(message_parts),
                "type": "warning" if failed_moves or skipped_count else "success",
                "sticky": bool(failed_moves),
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }
