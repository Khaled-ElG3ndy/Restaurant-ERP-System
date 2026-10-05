{
    "name": "Hosny Backend Theme",
    "summary": "Modern premium home menu for the Hosny backend",
    "version": "19.0.1.1.0",
    "category": "Themes/Backend",
    "license": "LGPL-3",
    "author": "TelNova Developers",
    "depends": ["muk_web_theme", "muk_web_appsbar", "pos_modern_ui"],
    "assets": {
        "web.assets_backend": [
            (
                "after",
                "muk_web_appsbar/static/src/webclient/appsbar/appsbar.js",
                "hosny_backend_theme/static/src/js/appsbar_toggle.js",
            ),
            (
                "after",
                "muk_web_appsbar/static/src/webclient/appsbar/appsbar.xml",
                "hosny_backend_theme/static/src/xml/appsbar_toggle.xml",
            ),
            (
                "after",
                "web/static/src/webclient/navbar/navbar.js",
                "hosny_backend_theme/static/src/js/navbar.js",
            ),
            (
                "after",
                "web/static/src/webclient/navbar/navbar.xml",
                "hosny_backend_theme/static/src/xml/navbar.xml",
            ),
            "hosny_backend_theme/static/src/js/sidebar.js",
            "hosny_backend_theme/static/src/scss/home_menu.scss",
            "hosny_backend_theme/static/src/scss/sidebar.scss",
            "hosny_backend_theme/static/src/scss/rtl_kanban.scss",
        ],
    },
    "installable": True,
    "application": False,
}
