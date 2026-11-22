"""Verdicts for a job that ComfyUI holds in its queue but says nothing about.

A long MiniMax H3 take is legitimately quiet: 243 frames at 864x480 on a 24 GB card spend about
twenty minutes on a single sampling step, while the app called that a hang after ten minutes and
told the user to restart ComfyUI — which would have thrown the running render away. So silence now
only raises a notice, and a job is dropped only when it has been silent for hours *and* the card
is doing nothing.
"""

QUIET_NOTICE = 600      # ten minutes without a progress event: say it is still working
QUIET_GIVE_UP = 7200    # two hours of silence with an idle card: that is a real hang


def job_verdict(in_queue, silent, gpu_busy, notice_after=QUIET_NOTICE, give_up_after=QUIET_GIVE_UP):
    """'ok' | 'notice' | 'stale' for a job ComfyUI still has.

    `gpu_busy` is True/False when the card could be read and None when it is unknown;
    an unknown card never fails a job, only an idle one after hours of silence does.
    """
    if not in_queue:
        return "stale"                      # ComfyUI does not have it at all
    if silent < notice_after:
        return "ok"
    if silent < give_up_after or gpu_busy is not False:
        return "notice"
    return "stale"
