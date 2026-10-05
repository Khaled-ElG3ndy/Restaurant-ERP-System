import re
import unicodedata
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .utils import boolean_search_domain


class PosMrpSourceProfile(models.Model):
    _name = "pos.mrp.source.profile"
    _description = "POS Manufacturing Component Source"
    _order = "name, id"

    name = fields.Char(string="Arabic Location Name", required=True, index=True)
    active = fields.Boolean(default=True)
    route_ids = fields.One2many(
        "pos.mrp.source.profile.route",
        "profile_id",
        string="Point of Sale Routes",
        copy=True,
    )
    route_count = fields.Integer(compute="_compute_route_status")
    ready_for_all_pos = fields.Boolean(
        string="Ready for All Points of Sale",
        compute="_compute_route_status",
        search="_search_ready_for_all_pos",
    )
    missing_pos_names = fields.Char(
        string="Missing Points of Sale",
        compute="_compute_route_status",
    )

    _name_uniq = models.Constraint(
        "unique(name)",
        "The Arabic logical location name must be unique.",
    )

    @api.model
    def _get_routed_pos_configs(self):
        return self.env["pos.config"].with_context(active_test=False).search([
            ("active", "=", True),
            ("auto_create_mrp_from_pos", "=", True),
        ])

    def _get_missing_pos_configs(self):
        self.ensure_one()
        configs = self._get_routed_pos_configs()
        return configs - self.route_ids.mapped("pos_config_id")

    @api.depends("route_ids", "route_ids.pos_config_id", "route_ids.location_id")
    def _compute_route_status(self):
        for profile in self:
            missing = profile._get_missing_pos_configs()
            profile.route_count = len(profile.route_ids)
            profile.ready_for_all_pos = not missing and bool(profile.route_ids)
            profile.missing_pos_names = ", ".join(missing.mapped("display_name"))

    @api.model
    def _search_ready_for_all_pos(self, operator, value):
        ready_ids = self.search([]).filtered(lambda profile: profile.ready_for_all_pos).ids
        return boolean_search_domain(ready_ids, operator, value)

    @api.model
    def _recompute_ready_for_all_pos(self):
        # Non-stored by design; invalidating keeps already-open forms consistent.
        self.invalidate_model(["ready_for_all_pos", "missing_pos_names", "route_count"])

    def _get_location_for_pos_config(self, pos_config):
        self.ensure_one()
        pos_config.ensure_one()
        routes = self.route_ids.filtered(lambda route: route.pos_config_id == pos_config)
        if not routes:
            raise UserError(
                _(
                    "The component source '%(profile)s' has no stock location configured for "
                    "Point of Sale '%(point_of_sale)s'.",
                    profile=self.display_name,
                    point_of_sale=pos_config.display_name,
                )
            )
        if len(routes) > 1:
            raise UserError(
                _(
                    "The component source '%(profile)s' has more than one route for "
                    "Point of Sale '%(point_of_sale)s'.",
                    profile=self.display_name,
                    point_of_sale=pos_config.display_name,
                )
            )
        location = routes.location_id
        if not location.active or location.usage != "internal" or not location.pos_mrp_is_leaf:
            raise UserError(
                _(
                    "The location '%(location)s' configured for '%(profile)s' must be an active "
                    "internal leaf location.",
                    location=location.display_name,
                    profile=self.display_name,
                )
            )
        location_company = location.company_id
        warehouse_company = location.warehouse_id.company_id
        if (
            location_company and location_company != pos_config.company_id
        ) or (
            warehouse_company and warehouse_company != pos_config.company_id
        ):
            raise UserError(
                _(
                    "The location '%(location)s' configured for '%(profile)s' does not belong "
                    "to the company of Point of Sale '%(point_of_sale)s'.",
                    location=location.display_name,
                    profile=self.display_name,
                    point_of_sale=pos_config.display_name,
                )
            )
        return location

    @staticmethod
    def _arabic_key(value):
        value = unicodedata.normalize("NFKD", value or "")
        value = "".join(char for char in value if not unicodedata.combining(char))
        value = value.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"}))
        return re.sub(r"[^\w\u0600-\u06ff]+", " ", value, flags=re.UNICODE).strip().lower()

    @classmethod
    def _clean_location_name(cls, location_name, branch_labels=()):
        parts = [part.strip() for part in (location_name or "").split("/") if part.strip()]
        arabic_parts = [part for part in parts if re.search(r"[\u0600-\u06ff]", part)]
        name = arabic_parts[-1] if arabic_parts else (parts[-1] if parts else location_name or "")

        removable = {"جدة", "جده", "المدينة", "المدينه", "الرياض", "رياض"}
        removable.update(label for label in branch_labels if label)
        for label in sorted(removable, key=len, reverse=True):
            name = re.sub(rf"(?<![\u0600-\u06ff]){re.escape(label)}(?![\u0600-\u06ff])", " ", name)

        name = re.sub(r"(?<![\u0600-\u06ff])مخز\s+ن(?![\u0600-\u06ff])", "مخزن", name)
        name = re.sub(r"\s*[-–—]+\s*$", "", name)
        name = re.sub(r"\s+", " ", name).strip(" -–—/")
        return name

    @api.model
    def _get_config_branch_labels(self, config):
        words = re.findall(r"[\u0600-\u06ff]+", config.name or "")
        stop_words = {"مطعم", "حسني", "نقطة", "البيع", "فرع"}
        labels = [word for word in words if word not in stop_words]
        return labels[-1:] or words[-1:]

    @api.model
    def _sync_profiles_from_leaf_locations(self):
        """Create/update complete logical profiles from paired branch leaf locations."""
        configs = self._get_routed_pos_configs()
        if not configs:
            return self

        labels_by_config = {
            config.id: self._get_config_branch_labels(config)
            for config in configs
        }
        all_labels = [label for labels in labels_by_config.values() for label in labels]
        leaf_locations = self.env["stock.location"].with_context(active_test=False).browse(
            self.env["stock.location"]._get_pos_mrp_leaf_location_ids()
        ).filtered("active")

        # Learn technical branch path segments (for example JED/MAD) from the
        # locations that already carry the POS branch label. This also pairs
        # leaf locations whose own name has no city suffix, such as dry storage.
        candidate_segments = defaultdict(set)
        segment_owners = defaultdict(set)
        for config in configs:
            label_keys = [self._arabic_key(label) for label in labels_by_config[config.id]]
            for location in leaf_locations:
                raw_name = location.complete_name or location.name
                if not any(label_key in self._arabic_key(raw_name) for label_key in label_keys):
                    continue
                for segment in [part.strip() for part in raw_name.split("/")[:-1] if part.strip()]:
                    segment_key = self._arabic_key(segment)
                    if segment_key:
                        candidate_segments[config.id].add(segment_key)
                        segment_owners[segment_key].add(config.id)
        unique_segments_by_config = {
            config.id: {
                segment
                for segment in candidate_segments[config.id]
                if segment_owners[segment] == {config.id}
            }
            for config in configs
        }

        grouped = defaultdict(lambda: defaultdict(lambda: self.env["stock.location"]))
        display_names = {}
        for location in leaf_locations:
            raw_name = location.complete_name or location.name
            raw_key = self._arabic_key(raw_name)
            path_segment_keys = {
                self._arabic_key(part)
                for part in raw_name.split("/")[:-1]
                if part.strip()
            }
            matching_configs = configs.filtered(
                lambda config: (
                    any(
                        self._arabic_key(label) in raw_key
                        for label in labels_by_config[config.id]
                    )
                    or bool(path_segment_keys & unique_segments_by_config[config.id])
                )
            )
            if len(matching_configs) != 1:
                continue
            clean_name = self._clean_location_name(raw_name, all_labels)
            clean_key = self._arabic_key(clean_name)
            if not clean_key:
                continue
            grouped[clean_key][matching_configs.id] |= location
            display_names.setdefault(clean_key, clean_name)

        synced_profiles = self
        required_config_ids = set(configs.ids)
        for clean_key, locations_by_config in grouped.items():
            if set(locations_by_config) != required_config_ids:
                continue
            if any(len(locations) != 1 for locations in locations_by_config.values()):
                continue

            name = display_names[clean_key]
            profile = self.search([("name", "=", name)], limit=1)
            if not profile:
                profile = self.create({"name": name})
            for config in configs:
                location = locations_by_config[config.id]
                route = profile.route_ids.filtered(lambda item: item.pos_config_id == config)
                if route:
                    route.location_id = location.id
                else:
                    self.env["pos.mrp.source.profile.route"].create({
                        "profile_id": profile.id,
                        "pos_config_id": config.id,
                        "location_id": location.id,
                    })
            synced_profiles |= profile

        return synced_profiles

    def action_sync_from_locations(self):
        profiles = self._sync_profiles_from_leaf_locations()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Location routes synchronized"),
                "message": _("%s complete logical locations are available.", len(profiles)),
                "type": "success",
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }


class PosMrpSourceProfileRoute(models.Model):
    _name = "pos.mrp.source.profile.route"
    _description = "POS Manufacturing Component Source Route"
    _order = "pos_config_id, id"

    profile_id = fields.Many2one(
        "pos.mrp.source.profile",
        required=True,
        ondelete="cascade",
        index=True,
    )
    pos_config_id = fields.Many2one(
        "pos.config",
        string="Point of Sale",
        required=True,
        ondelete="cascade",
        index=True,
        domain="[('auto_create_mrp_from_pos', '=', True)]",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Physical Stock Location",
        required=True,
        ondelete="restrict",
        domain="[('usage', '=', 'internal'), ('pos_mrp_is_leaf', '=', True)]",
    )

    _profile_pos_config_uniq = models.Constraint(
        "unique(profile_id, pos_config_id)",
        "Only one physical location can be configured per logical location and Point of Sale.",
    )

    @api.constrains("location_id", "pos_config_id")
    def _check_location_is_internal_leaf(self):
        for route in self:
            location = route.location_id
            if location.usage != "internal" or not location.pos_mrp_is_leaf:
                raise ValidationError(
                    _("The physical stock location must be an internal leaf location.")
                )
            if (
                location.company_id and location.company_id != route.pos_config_id.company_id
            ) or (
                location.warehouse_id.company_id
                and location.warehouse_id.company_id != route.pos_config_id.company_id
            ):
                raise ValidationError(
                    _(
                        "The physical stock location must belong to the company of the selected "
                        "Point of Sale."
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        routes = super().create(vals_list)
        routes.mapped("profile_id")._recompute_ready_for_all_pos()
        return routes

    def write(self, vals):
        profiles = self.mapped("profile_id")
        result = super().write(vals)
        (profiles | self.mapped("profile_id"))._recompute_ready_for_all_pos()
        return result

    def unlink(self):
        profiles = self.mapped("profile_id")
        result = super().unlink()
        profiles._recompute_ready_for_all_pos()
        return result
