"""Everything sport-specific lives in sports/<sport>/: decisions and prompts, event reading, rulebook.
The pipeline reaches a sport only through these two functions."""
import importlib


def decisions(sport):
    return importlib.import_module(f"sports.{sport}.decisions")


def events(sport):
    return importlib.import_module(f"sports.{sport}.events")
