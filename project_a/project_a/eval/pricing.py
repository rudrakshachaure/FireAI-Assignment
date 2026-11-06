"""Gemini list prices used for the cost table. TODO-VERIFY: fill SOURCE_URL and DATE from the
official Gemini API pricing page before quoting any cost number. Free tier = $0 but rate limited."""
MODEL = "gemini-2.5-flash"
USD_PER_M_INPUT = 0.30     # TODO-VERIFY (paid tier, text input)
USD_PER_M_OUTPUT = 2.50    # TODO-VERIFY (paid tier, output incl. thinking)
SOURCE_URL = "TODO-VERIFY"
PRICE_DATE = "TODO-VERIFY"
FREE_TIER_RPM = "TODO-VERIFY"
