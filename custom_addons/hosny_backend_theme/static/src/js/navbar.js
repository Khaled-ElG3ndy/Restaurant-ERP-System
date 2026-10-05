/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { url } from "@web/core/utils/urls";
import { NavBar } from "@web/webclient/navbar/navbar";
import { HosnyAppsSidebar } from "./sidebar";

const SIDEBAR_STORAGE_KEY = "hosny_sidebar_collapsed";

patch(NavBar.prototype, {
    setup() {
        super.setup();
        this.appMenuService = useService("app_menu");

        // Initialize sidebar state
        this.sidebarCollapsed = localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true";
    },

    getHosnyAppsCount() {
        return this.appMenuService.getAppsMenuItems().length;
    },

    getHosnyCompanyName() {
        return user.activeCompany?.name || "Hosny";
    },

    hasHosnyCompanyLogo() {
        return Boolean(user.activeCompany?.has_appsbar_image);
    },

    getHosnyCompanyLogoUrl() {
        if (!this.hasHosnyCompanyLogo()) {
            return "";
        }
        return url("/web/image", {
            model: "res.company",
            field: "appbar_image",
            id: user.activeCompany.id,
        });
    },

    getHosnyCompanyInitials() {
        const name = this.getHosnyCompanyName().trim();
        if (!name) {
            return "H";
        }
        return name
            .split(/\s+/)
            .slice(0, 2)
            .map((part) => part[0])
            .join("")
            .toUpperCase();
    },

    getHosnyDateLabel() {
        return new Intl.DateTimeFormat("ar-EG", {
            weekday: "long",
            day: "numeric",
            month: "long",
        }).format(new Date());
    },

    isHosnyRtl() {
        if (typeof document === "undefined") {
            return false;
        }
        return document.documentElement.dir === "rtl" || document.body.dir === "rtl";
    },

    getHosnySidebarToggleIcon() {
        const rtl = this.isHosnyRtl();
        const pointsToOpenSide = this.sidebarCollapsed;
        const direction = pointsToOpenSide !== rtl ? "right" : "left";
        return `oi oi-chevron-${direction} fs-4`;
    },

    getHosnySidebarToggleTitle() {
        return this.sidebarCollapsed ? "Open Sidebar" : "Close Sidebar";
    },

    toggleSidebar() {
        this.sidebarCollapsed = !this.sidebarCollapsed;
        localStorage.setItem(SIDEBAR_STORAGE_KEY, String(this.sidebarCollapsed));
        // Trigger re-render
        this.render();
    },
});

