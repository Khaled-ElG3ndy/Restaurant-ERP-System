{
    "name": "Hosny HR Work Locations",
    "version": "19.0.1.0.2",
    "category": "Human Resources/Employees",
    "summary": "Controlled employee work locations and historical location snapshots",
    "author": "Hosny",
    "license": "LGPL-3",
    "depends": [
        "hosny_hr_payroll_ar",
        "hr_homeworking",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/work_location_data.xml",
        "views/hr_employee_views.xml",
        "views/hr_transaction_views.xml",
        "views/migration_report_views.xml",
    ],
    "pre_init_hook": "pre_init_hook",
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
