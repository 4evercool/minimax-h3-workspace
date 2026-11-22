"""The watchdog must not call a long sampling step a hang.

Seen in the field: a 243-frame take at 864x480 spent ~21 minutes on one step of eight, and the app
declared a hang after ten minutes, telling the user to restart ComfyUI — which would have destroyed
the render that was, in fact, running at 100 % GPU.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import watchdog  # noqa: E402


def test_short_silence_is_fine():
    assert watchdog.job_verdict(True, 30, True) == "ok"
    assert watchdog.job_verdict(True, watchdog.QUIET_NOTICE - 1, False) == "ok"


def test_long_step_raises_a_notice_not_an_error():
    # 21 minutes without an event, the card is busy: exactly the case that used to be called a hang
    assert watchdog.job_verdict(True, 21 * 60, True) == "notice"
    assert watchdog.job_verdict(True, 3600, True) == "notice"


def test_unknown_gpu_never_fails_the_job():
    assert watchdog.job_verdict(True, 10 * 3600, None) == "notice"


def test_hours_of_silence_with_an_idle_card_is_a_hang():
    assert watchdog.job_verdict(True, watchdog.QUIET_GIVE_UP + 1, False) == "stale"


def test_a_job_comfyui_does_not_have_is_stale():
    assert watchdog.job_verdict(False, 0, True) == "stale"


def test_thresholds_are_overridable():
    assert watchdog.job_verdict(True, 120, True, notice_after=600) == "ok"
    assert watchdog.job_verdict(True, 900, True, give_up_after=60, notice_after=60) == "notice"
