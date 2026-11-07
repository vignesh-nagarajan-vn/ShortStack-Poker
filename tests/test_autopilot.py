"""Autopilot detection: triggers on check/fold runs, resets on any call or raise."""

from bot.autopilot import MIN_FOLDS, STREAK, AutopilotDetector
from bot.opponent import Step
from game import Action, Street


def _feed(det, pattern):
    for action, facing in pattern:
        det.observe([Step(Street.FLOP, False, action)], [facing])


def test_triggers_after_check_fold_run():
    det = AutopilotDetector()
    _feed(det, [(Action.FOLD, True)] * MIN_FOLDS + [(Action.CHECK_CALL, False)] * (STREAK - MIN_FOLDS))
    assert det.active


def test_checks_alone_do_not_trigger():
    det = AutopilotDetector()
    _feed(det, [(Action.CHECK_CALL, False)] * 50)
    assert not det.active


def test_a_call_resets():
    det = AutopilotDetector()
    _feed(det, [(Action.FOLD, True)] * 20)
    assert det.active
    _feed(det, [(Action.CHECK_CALL, True)])
    assert not det.active
