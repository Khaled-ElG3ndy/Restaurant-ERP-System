import { getActiveActions } from "@web/views/utils";

export class AttendanceTimelineArchParser {
    parse(xmlDoc) {
        return {
            activeActions: getActiveActions(xmlDoc),
            title:
                xmlDoc.getAttribute("string") ||
                "Attendance Timeline",
        };
    }
}

