"""Static-analysis tool wrappers (pylint, bandit, radon).

Each module exposes one async function that runs the tool as a subprocess and
returns a list of structured findings. Failures are swallowed: callers always
get a list (possibly empty) and a printed warning.
"""
