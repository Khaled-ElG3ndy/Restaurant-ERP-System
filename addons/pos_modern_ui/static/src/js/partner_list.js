/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { normalize } from "@web/core/l10n/utils";
import { _t } from "@web/core/l10n/translation";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";
import { PartnerLine } from "@point_of_sale/app/screens/partner_list/partner_line/partner_line";

const HOSNY_FAVORITE_LIMIT = 5;
const HOSNY_FAVORITE_STORAGE_KEY = "hosny_pos_partner_favorites";

PartnerLine.props = [
    ...PartnerLine.props,
    "isFavorite?",
    "onToggleFavorite?",
];

patch(PartnerList.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.favoritePartnerIds = this._hosnyReadFavoritePartnerIds();
        this._hosnyLoadFavoritePartners();
    },

    _hosnyFavoriteStorageKey() {
        const dbName = globalThis.odoo?.session_info?.db || globalThis.odoo?.db || "default";
        const configId = this.pos.config?.id || globalThis.odoo?.pos_config_id || "default";
        return `${HOSNY_FAVORITE_STORAGE_KEY}:${dbName}:${configId}`;
    },

    _hosnyNormalizeFavoriteIds(ids) {
        const normalized = [];
        for (const id of ids || []) {
            const partnerId = Number(id);
            if (Number.isInteger(partnerId) && partnerId > 0 && !normalized.includes(partnerId)) {
                normalized.push(partnerId);
            }
        }
        return normalized.slice(0, HOSNY_FAVORITE_LIMIT);
    },

    _hosnyReadFavoritePartnerIds() {
        try {
            const rawValue = globalThis.localStorage?.getItem(this._hosnyFavoriteStorageKey());
            return this._hosnyNormalizeFavoriteIds(JSON.parse(rawValue || "[]"));
        } catch {
            return [];
        }
    },

    _hosnyWriteFavoritePartnerIds(ids) {
        try {
            globalThis.localStorage?.setItem(
                this._hosnyFavoriteStorageKey(),
                JSON.stringify(this._hosnyNormalizeFavoriteIds(ids))
            );
        } catch {
            // Ignore unavailable browser storage so the customer list remains usable.
        }
    },

    _hosnySetFavoritePartnerIds(ids) {
        const normalized = this._hosnyNormalizeFavoriteIds(ids);
        this.state.favoritePartnerIds.splice(
            0,
            this.state.favoritePartnerIds.length,
            ...normalized
        );
        this._hosnyWriteFavoritePartnerIds(normalized);
    },

    async _hosnyLoadFavoritePartners() {
        const missingIds = this.state.favoritePartnerIds.filter(
            (id) => !this.pos.models["res.partner"].get(id)
        );
        if (!missingIds.length) {
            return;
        }
        try {
            await this.pos.data.read("res.partner", missingIds);
            this._hosnySetFavoritePartnerIds(
                this.state.favoritePartnerIds.filter((id) =>
                    this.pos.models["res.partner"].get(id)
                )
            );
        } catch {
            // Favorites are an enhancement; failed lazy loading should not block checkout.
        }
    },

    get hosnyFavoritePartners() {
        return this.state.favoritePartnerIds
            .map((id) => this.pos.models["res.partner"].get(id))
            .filter(Boolean)
            .slice(0, HOSNY_FAVORITE_LIMIT);
    },

    hosnyIsFavoritePartner(partner) {
        return this.state.favoritePartnerIds.includes(Number(partner?.id));
    },

    hosnyToggleFavoritePartner(partner) {
        const partnerId = Number(partner?.id);
        if (!Number.isInteger(partnerId) || partnerId <= 0) {
            return;
        }

        if (this.hosnyIsFavoritePartner(partner)) {
            this._hosnySetFavoritePartnerIds(
                this.state.favoritePartnerIds.filter((id) => id !== partnerId)
            );
            return;
        }

        const nextFavoriteIds = this.state.favoritePartnerIds.filter((id) => id !== partnerId);
        if (nextFavoriteIds.length >= HOSNY_FAVORITE_LIMIT) {
            this.notification.add(
                _t("لا يمكن إضافة أكثر من 5 عملاء للمفضلة. احذف عميلًا من المفضلة أولًا."),
                { type: "warning" }
            );
            return;
        }
        nextFavoriteIds.unshift(partnerId);
        this._hosnySetFavoritePartnerIds(nextFavoriteIds);
    },

    _hosnyPartnerDisplayKey(partner) {
        const name = normalize(String(partner?.name || ""))
            .replace(/\s+/g, " ")
            .trim()
            .toLowerCase();
        return name || `id:${partner?.id || ""}`;
    },

    _hosnyIsRemovedTestPartner(partner) {
        const name = normalize(String(partner?.name || ""))
            .replace(/\s+/g, " ")
            .trim()
            .toLowerCase();
        const email = normalize(String(partner?.email || ""))
            .replace(/\s+/g, " ")
            .trim()
            .toLowerCase();
        const removedExactNames = new Set(["123", "administrator", "gdfg", "gs"]);
        return (
            removedExactNames.has(name) ||
            name.includes("codex") ||
            name.includes("verification") ||
            name.includes("verify") ||
            email === "admin@hosny.com" ||
            email.endsWith("@invalid.local") ||
            email.includes(".verify.")
        );
    },

    _hosnyPartnerScore(partner) {
        let score = this.props.partner?.id === partner?.id ? 1000 : 0;
        for (const field of ["phone", "mobile", "email", "pos_contact_address", "parent_name"]) {
            if (partner?.[field]) {
                score += 1;
            }
        }
        return score;
    },

    _hosnyDeduplicatePartners(partners, existingKeys = new Set()) {
        const byKey = new Map();
        const order = [];
        for (const partner of partners || []) {
            if (this._hosnyIsRemovedTestPartner(partner)) {
                continue;
            }
            const key = this._hosnyPartnerDisplayKey(partner);
            if (!key || existingKeys.has(key)) {
                continue;
            }
            const current = byKey.get(key);
            if (!current) {
                byKey.set(key, partner);
                order.push(key);
                continue;
            }
            if (this._hosnyPartnerScore(partner) > this._hosnyPartnerScore(current)) {
                byKey.set(key, partner);
            }
        }
        return order.map((key) => byKey.get(key));
    },

    _hosnyInitialDisplayKeys() {
        return new Set(
            this._hosnyDeduplicatePartners(this.state.initialPartners).map((partner) =>
                this._hosnyPartnerDisplayKey(partner)
            )
        );
    },

    _hosnyCompactLoadedPartners() {
        const compact = this._hosnyDeduplicatePartners(
            this.state.loadedPartners,
            this._hosnyInitialDisplayKeys()
        );
        this.state.loadedPartners.splice(0, this.state.loadedPartners.length, ...compact);
    },

    getPartners(partners) {
        return this._hosnyDeduplicatePartners(super.getPartners(partners));
    },

    async getNewPartners() {
        const result = await super.getNewPartners(...arguments);
        this._hosnyCompactLoadedPartners();
        return this._hosnyDeduplicatePartners(result);
    },
});
