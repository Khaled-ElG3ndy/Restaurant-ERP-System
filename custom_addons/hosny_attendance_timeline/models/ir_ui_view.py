from lxml import etree

from odoo import _, fields, models


TIMELINE_VALID_ATTRIBUTES = {
    "__validate__",
    "class",
    "create",
    "delete",
    "edit",
    "js_class",
    "string",
}


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    type = fields.Selection(
        selection_add=[("attendance_timeline", "Timeline")]
    )

    def _validate_tag_attendance_timeline(
        self, node, name_manager, node_info
    ):
        if not node_info["validate"]:
            return

        for child in node.iterchildren(tag=etree.Element):
            if child.tag != "field":
                self._raise_view_error(
                    _(
                        "Attendance timeline children must be field nodes, "
                        "got %s",
                        child.tag,
                    ),
                    child,
                )

        invalid_attributes = set(node.attrib) - TIMELINE_VALID_ATTRIBUTES
        if invalid_attributes:
            self._raise_view_error(
                _(
                    "Invalid attendance timeline attributes "
                    "(%(invalid_attributes)s). Allowed attributes are "
                    "%(valid_attributes)s.",
                    invalid_attributes=", ".join(sorted(invalid_attributes)),
                    valid_attributes=", ".join(
                        sorted(TIMELINE_VALID_ATTRIBUTES)
                    ),
                ),
                node,
            )

    def _get_view_info(self):
        return {
            "attendance_timeline": {
                "icon": "fa fa-tasks",
                "multi_record": True,
            }
        } | super()._get_view_info()

