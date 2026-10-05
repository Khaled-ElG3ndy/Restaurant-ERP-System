import { useEffect } from "@odoo/owl";
import { useBus, useService } from "@web/core/utils/hooks";

import { Dropdown } from "@web/core/dropdown/dropdown";

const HOSNY_APPS_BACKGROUND_WEBP = "/muk_web_theme/static/src/img/hosny_apps_background.webp";
const HOSNY_APPS_BACKGROUND_JPG = "/muk_web_theme/static/src/img/hosny_apps_background.jpg";

let backgroundLoadPromise;

function ensureBackgroundPreloadLink() {
    if (document.getElementById("hosny-apps-background-preload")) {
        return;
    }
    const link = document.createElement("link");
    link.id = "hosny-apps-background-preload";
    link.rel = "preload";
    link.as = "image";
    link.href = HOSNY_APPS_BACKGROUND_WEBP;
    link.type = "image/webp";
    link.fetchPriority = "high";
    document.head.appendChild(link);
}

function preloadBackground() {
    if (backgroundLoadPromise) {
        return backgroundLoadPromise;
    }
    ensureBackgroundPreloadLink();
    backgroundLoadPromise = new Promise((resolve) => {
        const image = new Image();
        image.decoding = "async";
        image.fetchPriority = "high";
        image.onload = () => resolve(HOSNY_APPS_BACKGROUND_WEBP);
        image.onerror = () => resolve(HOSNY_APPS_BACKGROUND_JPG);
        image.src = HOSNY_APPS_BACKGROUND_WEBP;
    });
    return backgroundLoadPromise;
}

export class AppsMenu extends Dropdown {
    setup() {
    	super.setup();
    	this.commandPaletteOpen = false;
        this.commandService = useService("command");
    	this.imageUrl = HOSNY_APPS_BACKGROUND_WEBP;
        preloadBackground().then((imageUrl) => {
            this.imageUrl = imageUrl;
            this.applyBackground();
        });
        useEffect(
            (isOpen) => {
            	if (isOpen) {
            		const openMainPalette = (ev) => {
            	    	if (
            	    		!this.commandPaletteOpen &&
            	    		ev.key.length === 1 &&
            	    		!ev.ctrlKey &&
            	    		!ev.altKey
            	    	) {
	            	        this.commandService.openMainPalette(
            	        		{ searchValue: `/${ev.key}` }, 
            	        		() => { this.commandPaletteOpen = false; }
            	        	);
	            	    	this.commandPaletteOpen = true;
            	    	}
            		}
	            	window.addEventListener("keydown", openMainPalette);
	                return () => {
	                	window.removeEventListener("keydown", openMainPalette);
	                	this.commandPaletteOpen = false;
	                }
            	}
            },
            () => [this.state.isOpen]
		);
    	useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => {
			if (this.state.isOpen) {
				this.state.close();
			}
		});
    }
    applyBackground() {
        if (this.menuRef && this.menuRef.el) {
            this.menuRef.el.style.backgroundImage = `url('${this.imageUrl}')`;
        }
    }
    onOpened() {
		super.onOpened();
        this.applyBackground();
    }
}
