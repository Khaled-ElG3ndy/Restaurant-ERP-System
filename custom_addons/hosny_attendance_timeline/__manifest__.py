{
    "name": "Hosny Attendance Timeline",
    "version": "19.0.1.1.9",
    "category": "Human Resources/Attendances",
    "summary": "Interactive, virtualized attendance timeline",
    "author": "Hosny",
    "license": "LGPL-3",
    "depends": [
        "web",
        "bus",
        "hr_attendance",
    ],
    "data": [
        "views/hr_attendance_timeline_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hosny_attendance_timeline/static/src/views/attendance_timeline/**/*.js",
            "hosny_attendance_timeline/static/src/views/attendance_timeline/**/*.xml",
            "hosny_attendance_timeline/static/src/views/attendance_timeline/**/*.scss",
        ],
        "web.assets_unit_tests": [
            "hosny_attendance_timeline/static/tests/**/*.test.js",
        ],
    },
    "installable": True,
    "application": False,
}
