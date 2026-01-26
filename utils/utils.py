import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)


def round_up_to_n_decimals(number, n):
    if n < 0:
        raise ValueError("Number of decimal places (n) cannot be negative.")

    multiplier = 10 ** n
    return math.ceil(number * multiplier) / multiplier


def calculate_formula(final_price: float, formula: Optional[str]) -> float:
    if not formula:
        return 0.0
    try:
        # Replace 'X' with the final_price in the formula
        expression = formula.replace('X', str(final_price))
        return eval(expression)  # Evaluate the formula
    except Exception as e:
        logger.error(f"Invalid wholesale formula '{formula}': {e}")
        return 0.0
