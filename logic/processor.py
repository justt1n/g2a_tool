import logging
import random
from typing import Optional

from models.logic_models import PayloadResult, CompareTarget
from models.sheet_models import Payload
from services.analyze_g2a_competition import CompetitionAnalysisService
from services.g2a_service import G2AService
from utils.g2a_logger import get_g2a_log_string
from utils.parser import get_prod_id, get_offer_id
from utils.utils import round_up_to_n_decimals

logger = logging.getLogger(__name__)


class G2AProcessor:
    def __init__(self, g2a_service: G2AService, analysis_service: CompetitionAnalysisService):
        self.g2a_service = g2a_service
        self.analysis_service = analysis_service

    def _calc_final_price(self, payload: Payload, price: Optional[float]) -> float:
        if price is None:
            price = payload.fetched_max_price if payload.fetched_max_price is not None else float('inf')
            logger.info(f"No competitive price, using fetched max price: {price:.3f}")

        if price == float('inf'):  # Trường hợp không có giá nào để tính
            return payload.fetched_max_price

        if payload.min_price_adjustment is not None and payload.max_price_adjustment is not None:
            min_adj = min(payload.min_price_adjustment, payload.max_price_adjustment)
            max_adj = max(payload.min_price_adjustment, payload.max_price_adjustment)
            d_price = random.uniform(min_adj, max_adj)
            price -= d_price

        if payload.fetched_min_price is not None:
            price = max(price, payload.fetched_min_price)

        if payload.fetched_max_price is not None:
            price = min(price, payload.fetched_max_price)

        if payload.price_rounding is not None:
            price = round_up_to_n_decimals(price, payload.price_rounding)

        return price

    def _validate_payload(self, payload: Payload) -> bool:
        if not payload.product_name:
            logger.warning("Payload validation failed: product_name is required.")
            return False
        if payload.price_rounding is not None and payload.price_rounding < 0:
            logger.warning("Payload validation failed: price_rounding cannot be negative.")
            return False
        if payload.product_compare is None:
            logger.warning("Payload validation failed: product_compare is required for comparison.")
            return False
        return True

    async def process_single_payload(self, payload: Payload) -> PayloadResult:
        if not self._validate_payload(payload):
            return PayloadResult(status=0, payload=payload, log_message="Payload validation failed.")

        try:
            if not payload.is_compare_enabled:
                logger.info(f"Skipping comparison for product: {payload.product_name}")
                if payload.fetched_min_price is None:
                    msg = "Cannot set final price without fetched_min_price when comparison is disabled."
                    logger.warning(msg)
                    return PayloadResult(status=0, payload=payload, log_message=msg)
                final_price = round_up_to_n_decimals(payload.fetched_min_price, payload.price_rounding)
                log_str = get_g2a_log_string(mode="not_compare", payload=payload, final_price=final_price)
                return PayloadResult(status=1, payload=payload,
                                     final_price=CompareTarget(name="No Comparison", price=final_price),
                                     log_message=log_str)

            prod_id_to_compare = get_prod_id(payload.product_compare)
            if not prod_id_to_compare:
                msg = f"Invalid G2A product compare URL: {payload.product_compare}"
                logger.warning(msg)
                return PayloadResult(status=0, payload=payload, log_message=msg)

            product_offers = await self.g2a_service.get_compare_price(prod_id_to_compare)
            if not product_offers:
                msg = f"No competition data found for product: {payload.product_name}"
                logger.warning(msg)
                final_price = self._calc_final_price(payload, None)
                return PayloadResult(status=1, payload=payload,
                                     final_price=CompareTarget(name="No Competition", price=final_price),
                                     log_message=msg)

            analysis_result = self.analysis_service.analyze_g2a_competition(payload, product_offers)

            edited_price = self._calc_final_price(payload, analysis_result.competitive_price)

            min_price_value = payload.get_min_price_value()
            if min_price_value is not None and edited_price < min_price_value:
                logger.info(
                    f"Final price ({edited_price:.3f}) is below min_price ({min_price_value:.3f}), not updating.")
                log_str = get_g2a_log_string("below_min", payload, edited_price, analysis_result)
                return PayloadResult(status=0, payload=payload, final_price=None, log_message=log_str)

            if min_price_value is None:
                logger.info("No min_price set, not updating.")
                log_str = get_g2a_log_string("no_min_price", payload, edited_price, analysis_result)
                return PayloadResult(status=0, payload=payload, final_price=None, log_message=log_str)

            offer_id = get_offer_id(payload.product_id)
            if not offer_id:
                msg = f"Could not parse your offer ID from product_id: {payload.product_id}"
                logger.error(msg)
                return PayloadResult(status=0, payload=payload, log_message=msg)

            offer_type = await self.g2a_service.get_offer_type(offer_id)
            if not offer_type:
                msg = f"Could not get offer type for {offer_id}."
                logger.error(msg)
                return PayloadResult(status=0, payload=payload, log_message=msg)

            log_str = get_g2a_log_string("compare", payload, edited_price, analysis_result)
            return PayloadResult(
                status=1,
                payload=payload,
                competition=product_offers,
                final_price=CompareTarget(name=analysis_result.competitor_name, price=edited_price),
                log_message=log_str,
                offer_id=offer_id,
                offer_type=offer_type
            )
        except Exception as e:
            logger.error(f"Error processing payload {payload.product_name}: {e}", exc_info=True)
            return PayloadResult(status=0, payload=payload, log_message=f"Error: {str(e)}", final_price=None)
