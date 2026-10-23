"""Data models and FMCSA code mappings for ELD output files."""

from dataclasses import dataclass
from datetime import datetime


# Event codes for event type 1 (change in duty status), Appendix A, Table 6.
DUTY_STATUS_CODES = {
    "off_duty": 1,
    "sleeper_berth": 2,
    "driving": 3,
    "on_duty_not_driving": 4,
}

# Appendix A, Table 8: event record status codes.
EVENT_RECORD_STATUS_CODES = {
    "active": 1,
    "inactive_changed": 2,
    "inactive_change_requested": 3,
    "inactive_change_rejected": 4,
}

# Appendix A, Table 7: event record origin codes.
EVENT_RECORD_ORIGIN_CODES = {
    "automatically_recorded_by_eld": 1,
    "edited_or_entered_by_driver": 2,
    "edit_requested_by_authenticated_non_driver": 3,
    "assumed_from_unidentified_driver_profile": 4,
}

# Appendix A, Table 6: event codes depend on the event type.
EVENT_CODES = {
    1: {
        "off_duty": 1,
        "sleeper_berth": 2,
        "driving": 3,
        "on_duty_not_driving": 4,
    },
    2: {
        "intermediate_log_conventional_location_precision": 1,
        "intermediate_log_reduced_location_precision": 2,
    },
    3: {
        "authorized_personal_use_of_cmv": 1,
        "yard_moves": 2,
        "special_driving_category_cleared": 0,
    },
    4: {
        "first_certification": 1,
        "recertification": "n (1-9; use 9 for further recertifications)",
    },
    5: {
        "driver_login": 1,
        "driver_logout": 2,
    },
    6: {
        "engine_power_up_conventional_location_precision": 1,
        "engine_power_up_reduced_location_precision": 2,
        "engine_shutdown_conventional_location_precision": 3,
        "engine_shutdown_reduced_location_precision": 4,
    },
    7: {
        "malfunction_logged": 1,
        "malfunction_cleared": 2,
        "data_diagnostic_event_logged": 3,
        "data_diagnostic_event_cleared": 4,
    },
}

# Appendix A, Table 9: ELD event type codes.
EVENT_TYPE_CODES = {
    "change_in_duty_status": 1,
    "intermediate_log": 2,
    "change_in_special_driving_category": 3,
    "driver_certification": 4,
    "driver_login_logout": 5,
    "engine_power_up_shutdown": 6,
    "malfunction_diagnostic": 7,
}


@dataclass(frozen=True)
class ELDEvent:
    """One row from the FMCSA ``ELD Event List`` output segment.

    Field order follows Appendix A, section 4.8.2.1.4. ``event_date`` and
    ``event_time`` are combined into ``event_datetime``; the raw date/time
    strings are retained by their parsed value only when needed for output.
    The event comment/annotation and driver location description are carried
    in the separate annotations/comments segment (section 4.8.2.1.5).
    """

    event_sequence_id_number: str
    event_record_status: int
    event_record_origin: int
    event_type: int
    event_code: int
    event_datetime: datetime
    accumulated_vehicle_miles: str
    elapsed_engine_hours: str
    event_latitude: str
    event_longitude: str
    distance_since_last_valid_coordinates: str
    corresponding_cmv_order_number: str
    record_originator_user_order_number: str
    eld_malfunction_indicator_status: int
    driver_data_diagnostic_event_indicator_status: int
    event_data_check_value: str
    line_data_check_value: str


