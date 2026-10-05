import { registry } from "@web/core/registry";

import { AttendanceTimelineArchParser } from "./attendance_timeline_arch_parser";
import { AttendanceTimelineController } from "./attendance_timeline_controller";
import { AttendanceTimelineRenderer } from "./attendance_timeline_renderer";

export const attendanceTimelineView = {
    type: "attendance_timeline",
    searchMenuTypes: ["filter", "groupBy", "favorite"],
    ArchParser: AttendanceTimelineArchParser,
    Controller: AttendanceTimelineController,
    Renderer: AttendanceTimelineRenderer,
    buttonTemplate: "hosny_attendance_timeline.ControlButtons",

    props(genericProps, view) {
        const { arch } = genericProps;
        return {
            ...genericProps,
            archInfo: new view.ArchParser().parse(arch),
            Renderer: view.Renderer,
            buttonTemplate: view.buttonTemplate,
        };
    },
};

registry
    .category("views")
    .add("attendance_timeline", attendanceTimelineView);
