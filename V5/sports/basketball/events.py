"""Builds the event from the form. Basketball has no match data file yet."""
from sports import shared
from sports.basketball.decisions import DECISIONS


def from_form(decision, date="", fmt="", notes=""):
    return shared.form_event("basketball", DECISIONS, decision, date, fmt, notes)
