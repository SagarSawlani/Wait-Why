"""Builds the event from the form. Tennis has no match data file yet."""
from sports import shared
from sports.tennis.decisions import DECISIONS


def from_form(decision, date="", fmt="", notes=""):
    return shared.form_event("tennis", DECISIONS, decision, date, fmt, notes)
