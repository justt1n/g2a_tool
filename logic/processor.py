import logging
import random
from datetime import datetime
from typing import List

from models.eneba_models import CompetitionEdge
from models.logic_models import PayloadResult, CompareTarget, AnalysisResult
from models.sheet_models import Payload
from services.g2a_service import EnebaService
from utils.utils import round_up_to_n_decimals


class Processor:
    def __init__(self, g2a_service: EnebaService):
        self.g2a_service = g2a_service

    def _calc_final_price(self, payload: Payload, price: float) -> float:
        if price is None:
            price = round_up_to_n_decimals(payload.fetched_max_price, payload.price_rounding)
            logging.info(f"No product match, using fetched max price: {price:.3f}")
        if payload.min_price_adjustment is None or payload.max_price_adjustment is None:
            pass
        else:
            min_adj = min(payload.min_price_adjustment, payload.max_price_adjustment)
            max_adj = max(payload.min_price_adjustment, payload.max_price_adjustment)

            d_price = random.uniform(min_adj, max_adj)
            price = price - d_price

        if payload.fetched_min_price is not None:
            price = max(price, payload.fetched_min_price)

        if payload.fetched_max_price is not None:
            price = min(price, payload.fetched_max_price)

        if payload.price_rounding is not None:
            price = round_up_to_n_decimals(price, payload.price_rounding)

        return price

    def _validate_payload(self, payload: Payload) -> bool:
        if not payload.product_name:
            logging.warning("Payload validation failed: product_name is required.")
            return False
        if payload.price_rounding is not None and payload.price_rounding < 0:
            logging.warning("Payload validation failed: price_rounding cannot be negative.")
            return False
        if payload.min_price_adjustment is not None and payload.max_price_adjustment is not None:
            if payload.min_price_adjustment > payload.max_price_adjustment:
                logging.warning(
                    "Payload validation failed: min_price_adjustment cannot be greater than max_price_adjustment.")
                return False
        if payload.product_id is None:
            logging.warning("Payload validation failed: product_id is required.")
            return False
        if payload.product_compare is None:
            logging.warning("Payload validation failed: product_compare is required.")
            return False
        return True

    def process_single_payload(self, payload: Payload) -> PayloadResult:
        if not self._validate_payload(payload):
            return PayloadResult(payload=payload, log_message="Payload validation failed.")
        try:
            if not payload.is_compare_enabled:
                logging.info(f"Skipping comparison for product: {payload.product_name}")
                final_price = round_up_to_n_decimals(payload.fetched_min_price, payload.price_rounding)
                log_str = get_log_string(
                    mode="not_compare",
                    payload=payload,
                    final_price=final_price
                )
                return PayloadResult(
                    status=1,
                    payload=payload,
                    final_price=CompareTarget(name="No Comparison", price=final_price),
                    log_message=log_str
                )
            payload.product_compare = payload.product_compare.replace("https://", "").split("/")[1]
            product_competition = self.g2a_service.get_competition_by_slug(payload.product_compare)
            payload.prod_uuid = str(self.g2a_service.get_product_id_by_slug(payload.product_compare))
            payload.offer_id = self.g2a_service.get_offer_id_by_url(payload.product_id)
            if not product_competition:
                logging.warning(f"No competition data found for product: {payload.product_name}")
                return PayloadResult(payload=payload, log_message="No competition data found.")
            analysis_result = self.g2a_service.analyze_competition(payload, product_competition)
            edited_price = self._calc_final_price(payload, analysis_result.competitive_price)
            if payload.get_min_price_value() is not None and edited_price < payload.get_min_price_value():
                logging.info(
                    f"Final price ({edited_price:.3f}) is below min_price ({payload.get_min_price_value():.3f}), not updating.")
                log_str = get_log_string(
                    mode="below_min",
                    payload=payload,
                    final_price=edited_price,
                    analysis_result=analysis_result,
                    filtered_products=product_competition
                )
                return PayloadResult(
                    status=0,
                    payload=payload,
                    final_price=None,
                    log_message=log_str
                )
            elif payload.get_min_price_value() is None:
                logging.info("No min_price set, not updating.")
                log_str = get_log_string(
                    mode="no_min_price",
                    payload=payload,
                    final_price=edited_price,
                    analysis_result=analysis_result,
                    filtered_products=product_competition
                )
                return PayloadResult(
                    status=0,
                    payload=payload,
                    final_price=None,
                    log_message=log_str
                )
            log_str = get_log_string(
                mode="compare",
                payload=payload,
                final_price=edited_price,
                analysis_result=analysis_result,
                filtered_products=product_competition
            )
            return PayloadResult(
                status=1,
                payload=payload,
                competition=product_competition,
                final_price=CompareTarget(name=analysis_result.competitor_name, price=edited_price),
                log_message=log_str
            )
        except Exception as e:
            logging.error(f"Error processing payload {payload.product_name}: {e}")
            return PayloadResult(
                status=1,
                payload=payload,
                log_message=f"Error processing payload: {str(e)}",
                final_price=None
            )

    def do_payload(self, payload: Payload):
        payload_result = self.process_single_payload(payload)
        if payload_result.status == 1:
            #TODO: Implement the logic to update the product price in the database or API
            logging.info(
                f"Successfully processed payload for {payload.product_name}. Final price: {payload_result.final_price.price:.3f}")
            log_data = {
                'note': payload_result.log_message,
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        else:
            logging.error(f"Failed to process payload for {payload.product_name}. Error: {payload_result.log_message}")


def _analysis_log_string(
        payload: Payload,
        analysis_result: AnalysisResult = None,
        filtered_products: List[CompetitionEdge] = None
) -> str:
    log_parts = []
    if analysis_result.competitor_name is None:
        competitor_name = "Max price"
    else:
        competitor_name = analysis_result.competitor_name
    competitor_price = analysis_result.competitive_price
    if competitor_price is None or competitor_price == -1:
        competitor_price = payload.fetched_max_price
    if competitor_name and competitor_price is not None:
        log_parts.append(f"- GiaSosanh: {competitor_name} = {competitor_price:.6f}\n")

    price_min_str = f"{payload.fetched_min_price:.6f}" if payload.fetched_min_price is not None else "None"
    price_max_str = f"{payload.fetched_max_price:.6f}" if payload.fetched_max_price is not None else "None"
    log_parts.append(f"PriceMin = {price_min_str}, PriceMax = {price_max_str}\n")

    sellers_below = analysis_result.sellers_below_min
    if sellers_below:
        sellers_info = "; ".join([
                                     f"{s.node.merchant_name} = {s.node.price.price_no_commission} ({s.node.price.old_price_with_commission:.6f})\n"
                                     for s in sellers_below[:6] if
                                     s.node.merchant_name not in payload.fetched_black_list])
        log_parts.append(f"Seller giá nhỏ hơn min_price):\n {sellers_info}")

    log_parts.append("Top 4 sản phẩm:\n")
    sorted_product = sorted(filtered_products, key=lambda item: item.node.price.amount, reverse=False)
    for product in sorted_product[:4]:
        log_parts.append(f"- {product.node.merchant_name}: {product.node.price.amount:.6f}\n")

    return "".join(log_parts)


def get_log_string(
        mode: str,
        payload: Payload,
        final_price: float,
        analysis_result: AnalysisResult = None,
        filtered_products: List[CompetitionEdge] = None
) -> str:
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    log_parts = []
    if mode == "not_compare":
        log_parts = [
            timestamp,
            f"Không so sánh, cập nhật thành công {final_price:.3f}\n"
        ]
    elif mode == "compare":
        log_parts = [
            timestamp,
            f"Cập nhật thành công {final_price:.3f}\n"
        ]
        if analysis_result:
            log_parts.append(_analysis_log_string(payload, analysis_result, filtered_products))
    elif mode == "below_min":
        log_parts = [
            timestamp,
            f"Giá cuối cùng ({final_price:.3f}) nhỏ hơn giá tối thiểu ({payload.get_min_price_value():.3f}), không cập nhật.\n"
        ]
        if analysis_result:
            log_parts.append(_analysis_log_string(payload, analysis_result, filtered_products))
    elif mode == "no_min_price":
        log_parts = [
            timestamp,
            f"Không có min_price, không cập nhật.\n"
        ]
        if analysis_result:
            log_parts.append(_analysis_log_string(payload, analysis_result, filtered_products))
    return " ".join(log_parts)
