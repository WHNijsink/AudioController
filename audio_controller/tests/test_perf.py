"""Performance-hardening regression tests.

P1: a zero auto-switch timeout must not turn the auto_switch task into a
    100%-CPU busy loop (await asyncio.sleep(0) in a tight while True).
"""
from audio_controller import settings, controller


def test_zero_timeout_auto_switch_is_clamped_to_at_least_one_minute():
    s = settings.Settings()
    s.timeout_auto_switch = 0
    settings.validate_settings(s)
    assert s.timeout_auto_switch >= 1


def test_auto_switch_interval_never_zero_even_for_bad_stored_value():
    # Defence in depth: even if a 0 slips through, the loop's sleep interval has
    # a floor so it cannot spin the CPU.
    assert controller.auto_switch_interval_seconds(0) >= 1
    assert controller.auto_switch_interval_seconds(15) == 15 * 60
