"""Unit tests for daily ELD duty-status timeline construction."""

from datetime import date, datetime
import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).with_name("FMCSA Log Generator.py")
MODULE_SPEC = importlib.util.spec_from_file_location("fmcsa_log_generator", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise ImportError(f"Could not load {MODULE_PATH}")
fmcsa = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = fmcsa
MODULE_SPEC.loader.exec_module(fmcsa)


class BuildDailyTimelinesTests(unittest.TestCase):
    def make_event(
        self,
        event_date: date,
        hour: int,
        minute: int,
        status_code: int,
        *,
        event_type: int = 1,
        record_status: int = 1,
        sequence_id: str = "0001",
    ):
        """Build a minimal event object with the fields used by the timeline code."""
        return fmcsa.ELDEvent(
            event_sequence_id_number=sequence_id,
            event_record_status=record_status,
            event_record_origin=1,
            event_type=event_type,
            event_code=status_code,
            event_datetime=datetime(
                event_date.year, event_date.month, event_date.day, hour, minute
            ),
            accumulated_vehicle_miles="0",
            elapsed_engine_hours="0.0",
            event_latitude="",
            event_longitude="",
            distance_since_last_valid_coordinates="0",
            corresponding_cmv_order_number="1",
            record_originator_user_order_number="1",
            eld_malfunction_indicator_status=0,
            driver_data_diagnostic_event_indicator_status=0,
            event_data_check_value="00",
            line_data_check_value="00",
        )

    def test_full_offline_day_with_no_events(self):
        offline_day = date(2026, 10, 12)

        timelines = fmcsa.build_daily_timelines(
            [], start_date=offline_day, end_date=offline_day
        )

        # True: the requested offline date is included even without any events.
        self.assertTrue(offline_day in timelines)
        # False: an offline day must not contain a non-off-duty interval.
        self.assertFalse(any(
            interval.status != "off_duty" for interval in timelines[offline_day]
        ))
        self.assertEqual(
            timelines[offline_day],
            [fmcsa.DutyStatusInterval(0.0, 24.0, "off_duty")],
        )

    def test_sleeper_berth_for_ten_hours(self):
        day = date(2026, 10, 12)
        events = [
            self.make_event(day, 17, 0, 1),  # Off duty at 17:00.
            self.make_event(day, 7, 0, 2),   # Sleeper berth begins at 07:00.
        ]

        timeline = fmcsa.build_daily_timelines(events)[day]

        # True: sleeper berth spans exactly 10 hours, from 07:00 through 17:00.
        self.assertTrue(any(
            interval.status == "sleeper_berth"
            and interval.end_hour - interval.start_hour == 10.0
            for interval in timeline
        ))
        # False: no zero-length or backwards intervals should be produced.
        self.assertFalse(any(
            interval.start_hour >= interval.end_hour for interval in timeline
        ))
        self.assertEqual(
            timeline,
            [
                fmcsa.DutyStatusInterval(0.0, 7.0, "off_duty"),
                fmcsa.DutyStatusInterval(7.0, 17.0, "sleeper_berth"),
                fmcsa.DutyStatusInterval(17.0, 24.0, "off_duty"),
            ],
        )

    def test_next_day_begins_with_previous_day_final_status(self):
        first_day = date(2026, 10, 12)
        second_day = date(2026, 10, 13)
        events = [
            self.make_event(first_day, 20, 0, 2),  # Sleeper berth before midnight.
            self.make_event(second_day, 6, 0, 3),  # Driving starts at 06:00.
        ]

        timelines = fmcsa.build_daily_timelines(events)

        # True: the second day begins in the prior day's last status.
        self.assertTrue(timelines[second_day][0].status == "sleeper_berth")
        # False: it must not incorrectly reset to off duty at midnight.
        self.assertFalse(timelines[second_day][0].status == "off_duty")
        self.assertEqual(
            timelines[second_day],
            [
                fmcsa.DutyStatusInterval(0.0, 6.0, "sleeper_berth"),
                fmcsa.DutyStatusInterval(6.0, 24.0, "driving"),
            ],
        )

    def test_event_at_midnight_starts_day_at_new_status_without_zero_span(self):
        day = date(2026, 10, 12)
        events = [self.make_event(day, 0, 0, 4)]

        timeline = fmcsa.build_daily_timelines(events)[day]

        # True: a midnight event sets the status for the full day immediately.
        self.assertTrue(len(timeline) == 1 and timeline[0].start_hour == 0.0)
        # False: the midnight transition must not create a zero-length span.
        self.assertFalse(any(
            interval.start_hour == interval.end_hour for interval in timeline
        ))
        self.assertEqual(
            timeline,
            [fmcsa.DutyStatusInterval(0.0, 24.0, "on_duty_not_driving")],
        )

    def test_inactive_and_non_duty_events_do_not_change_timeline(self):
        day = date(2026, 10, 12)
        events = [
            self.make_event(day, 8, 0, 3, record_status=2),
            self.make_event(day, 9, 0, 3, event_type=2),
        ]

        timelines = fmcsa.build_daily_timelines(events, start_date=day, end_date=day)

        # True: ignored events leave the default off-duty interval intact.
        self.assertTrue(all(
            interval.status == "off_duty" for interval in timelines[day]
        ))
        # False: inactive or non-duty events must not create a driving span.
        self.assertFalse(any(
            interval.status == "driving" for interval in timelines[day]
        ))
        self.assertEqual(
            timelines[day],
            [fmcsa.DutyStatusInterval(0.0, 24.0, "off_duty")],
        )

    def test_unknown_duty_status_event_code_raises_clear_error(self):
        day = date(2026, 10, 12)
        event = self.make_event(day, 8, 0, 9, sequence_id="ABCD")

        with self.assertRaisesRegex(ValueError, "ABCD.*unknown duty-status.*9"):
            fmcsa.build_daily_timelines([event])

    def test_start_date_after_end_date_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "start_date must be on or before end_date"):
            fmcsa.build_daily_timelines(
                [], start_date=date(2026, 10, 13), end_date=date(2026, 10, 12)
            )


if __name__ == "__main__":
    unittest.main()
