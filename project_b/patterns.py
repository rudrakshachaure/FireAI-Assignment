"""Regexes shared by the profiler and the rule detectors."""
import re

ISO_DT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
ZIP5 = re.compile(r"^\d{5}$")
PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
SPACED_DIGITS = re.compile(r"(?:\d[\s.-]){6,}\d")          # "2 1 2 5 5 5 0 1 4 3"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
AT_DOT = re.compile(r"\b[\w.]+\s+at\s+\w+\s+dot\s+\w+", re.I)  # "jo at gmail dot com"
CLOSED_WORDS = re.compile(r"closed this|has been resolved|completed|resolved and closed", re.I)
PENDING_WORDS = re.compile(r"still|pending|being investigated|not yet|has not", re.I)
MOJIBAKE = re.compile("Ã|â€|\ufffd")
