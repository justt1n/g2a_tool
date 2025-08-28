from datetime import datetime

from models.logic_models import AnalysisResult
from models.sheet_models import Payload


def _g2a_analysis_log_string(
        payload: Payload,
        analysis_result: AnalysisResult
) -> str:
    log_parts = []

    competitor_price = analysis_result.competitive_price
    if competitor_price is None or competitor_price == float('inf'):
        competitor_name = "Max price (fallback)"
        competitor_price = payload.fetched_max_price
    else:
        competitor_name = analysis_result.competitor_name

    if competitor_name and competitor_price is not None:
        log_parts.append(f"- GiaSosanh: {competitor_name} = {competitor_price:.6f}\n")

    price_min_str = f"{payload.fetched_min_price:.6f}" if payload.fetched_min_price is not None else "None"
    price_max_str = f"{payload.fetched_max_price:.6f}" if payload.fetched_max_price is not None else "None"
    log_parts.append(f"PriceMin = {price_min_str}, PriceMax = {price_max_str}\n")

    sellers_below = analysis_result.sellers_below_min
    if sellers_below:
        sellers_info = "; ".join([
            f"{s.get_seller_name()} = {s.get_price_value():.6f}"
            for s in sellers_below[:6]
        ])
        log_parts.append(f"Seller giá nhỏ hơn min_price:\n {sellers_info}\n")

    log_parts.append("Top 4 sellers:\n")
    sorted_offers = sorted(analysis_result.top_sellers_for_log, key=lambda o: o.get_price_value())
    for offer in sorted_offers[:4]:
        log_parts.append(f"- {offer.get_seller_name()}: {offer.get_price_value():.6f}\n")

    return "".join(log_parts)


def get_g2a_log_string(
        mode: str,
        payload: Payload,
        final_price: float,
        analysis_result: AnalysisResult = None
) -> str:
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    log_parts = []

    base_message = ""
    if mode == "not_compare":
        base_message = f"Không so sánh, cập nhật thành công {final_price:.3f}\n"
    elif mode == "compare":
        base_message = f"Cập nhật thành công {final_price:.3f}\n"
    elif mode == "below_min":
        min_val = payload.get_min_price_value()
        base_message = f"Giá cuối cùng ({final_price:.3f}) nhỏ hơn giá tối thiểu ({min_val:.3f}), không cập nhật.\n"
    elif mode == "no_min_price":
        base_message = "Không có min_price, không cập nhật.\n"

    log_parts.append(f"{timestamp} {base_message}")

    if analysis_result:
        log_parts.append(_g2a_analysis_log_string(payload, analysis_result))

    return "".join(log_parts)
