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
        # Reset giá trị điều chỉnh mỗi lần tính toán lại
        payload.applied_adj = 0.0

        if price is None:
            price = payload.fetched_max_price if payload.fetched_max_price is not None else float('inf')

        if price == float('inf'):
            return payload.fetched_max_price

        # --- TÍNH TOÁN RANDOM VÀ LƯU VÀO PAYLOAD ---
        if payload.min_price_adjustment is not None and payload.max_price_adjustment is not None:
            min_adj = min(payload.min_price_adjustment, payload.max_price_adjustment)
            max_adj = max(payload.min_price_adjustment, payload.max_price_adjustment)

            # Tính số random
            d_price = random.uniform(min_adj, max_adj)

            # LƯU VÀO PAYLOAD ĐỂ DÙNG LẠI HOẶC LOG
            payload.applied_adj = d_price

            # Trừ giá
            price -= d_price

        if payload.fetched_min_price is not None:
            price = max(price, payload.fetched_min_price)

        if payload.fetched_max_price is not None:
            price = min(price, payload.fetched_max_price)

        if payload.price_rounding is not None:
            price = round_up_to_n_decimals(price, payload.price_rounding)

        return price

    def _validate_payload(self, payload: Payload) -> bool:
        # (Giữ nguyên)
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

    def _is_price_diff_significant(self, price1: float, price2: float, payload: Payload) -> bool:
        """
        True = CẦN Update (Lệch lớn).
        False = KHÔNG Update (Lệch nhỏ do random/làm tròn).
        """
        step = 0.01
        if payload.price_rounding is not None:
            step = 1 / (10 ** payload.price_rounding)

        random_noise = 0.0
        if payload.min_price_adjustment is not None and payload.max_price_adjustment is not None:
            random_noise = abs(payload.max_price_adjustment - payload.min_price_adjustment)

        # Ngưỡng = Biên độ dao động Random + Sai số làm tròn
        threshold = random_noise + (step * 0.5)
        threshold = max(threshold, step * 1.5)  # Tối thiểu chặn được sai số 1 đơn vị

        return abs(price1 - price2) > threshold

    # --- HÀM XỬ LÝ CHÍNH ---
    async def process_single_payload(self, payload: Payload) -> PayloadResult:
        if not self._validate_payload(payload):
            return PayloadResult(status=0, payload=payload, log_message="Payload validation failed.")

        try:
            # =========================================================================
            # BƯỚC 1: CHUẨN BỊ DỮ LIỆU (CHẠY CHO MỌI MODE)
            # =========================================================================

            # 1.1 Lấy thông tin Offer hiện tại (Bắt buộc)
            offer_id = get_offer_id(payload.product_id)
            if not offer_id:
                return PayloadResult(status=0, payload=payload,
                                     log_message=f"Invalid Offer ID from {payload.product_id}")

            current_details = await self.g2a_service.get_offer_details_full(offer_id)
            if not current_details or not current_details.data:
                return PayloadResult(status=0, payload=payload, log_message="Fetch Current Details Failed")

            # SET VÀO PAYLOAD ĐỂ DÙNG CHUNG
            payload.current_price = current_details.data.get_base_price()
            offer_type = current_details.data.type

            mode = payload.get_compare_mode

            # =========================================================================
            # MODE 0: NOT COMPARE
            # =========================================================================
            if mode == 0:
                logger.info(f"Mode 0: Not Compare {payload.product_name}")
                if payload.fetched_min_price is None:
                    return PayloadResult(status=0, payload=payload, log_message="Mode 0: No Min Price")

                final_price = round_up_to_n_decimals(payload.fetched_min_price, payload.price_rounding)
                payload.applied_adj = 0.0

                if not self._is_price_diff_significant(payload.current_price, final_price, payload):
                    log_str = get_g2a_log_string("equal", payload, payload.current_price)
                    return PayloadResult(status=2, payload=payload, log_message=log_str, offer_id=offer_id)

                log_str = get_g2a_log_string("not_compare", payload, final_price)
                return PayloadResult(status=1, payload=payload,
                                     final_price=CompareTarget(name="No Comparison", price=final_price),
                                     log_message=log_str, offer_id=offer_id, offer_type=offer_type)

            # =========================================================================
            # CHUẨN BỊ DỮ LIỆU ĐỐI THỦ (CHO MODE 1 & 2)
            # =========================================================================
            prod_id_to_compare = get_prod_id(payload.product_compare)
            if not prod_id_to_compare:
                return PayloadResult(status=0, payload=payload, log_message="Invalid Compare URL")

            product_offers = await self.g2a_service.get_compare_price(prod_id_to_compare)

            # Tính toán giá mục tiêu (Target Price)
            if not product_offers:
                logger.warning(f"No competition found for {payload.product_name}")
                target_price = self._calc_final_price(payload, None)
                competitor_name = "No Competition"
                analysis_result = None
            else:
                analysis_result = self.analysis_service.analyze_g2a_competition(payload, product_offers)
                target_price = self._calc_final_price(payload, analysis_result.competitive_price)
                competitor_name = analysis_result.competitor_name

            # Xử lý Min Price Protection (Chung cho cả 2 mode)
            min_price_value = payload.get_min_price_value()

            if min_price_value is not None:
                # Case A: Giá hiện tại bị lủng đáy -> BẮT BUỘC UPDATE LÊN MIN
                if payload.current_price < min_price_value:
                    logger.info(f"Current ({payload.current_price}) < Min. Force update to Min.")
                    target_price = min_price_value
                    payload.applied_adj = 0.0  # Reset adj
                # Case B: Target tính ra thấp hơn Min (nhưng giá hiện tại an toàn) -> CHẶN
                elif target_price < min_price_value:
                    log_str = get_g2a_log_string("below_min", payload, target_price, analysis_result)
                    return PayloadResult(status=0, payload=payload, final_price=None, log_message=log_str)
            elif min_price_value is None:
                # Không có Min Price thì không dám chạy
                log_str = get_g2a_log_string("no_min_price", payload, target_price, analysis_result)
                return PayloadResult(status=0, payload=payload, final_price=None, log_message=log_str)

            # =========================================================================
            # MODE 1: LUÔN THEO SAU (Standard Follow)
            # Logic: Luôn chỉnh giá về Target, trừ khi đã khớp (do random).
            # =========================================================================
            if mode == 1:
                # Chỉ kiểm tra xem giá có khớp không (trong phạm vi random)
                if not self._is_price_diff_significant(payload.current_price, target_price, payload):
                    # Đã tối ưu -> Không chỉnh
                    log_str = get_g2a_log_string("equal", payload, payload.current_price, analysis_result)
                    return PayloadResult(status=2, payload=payload, log_message=log_str, offer_id=offer_id)

                # Nếu lệch -> Update (Tăng hoặc Giảm đều Update)
                log_str = get_g2a_log_string("compare", payload, target_price, analysis_result)
                return PayloadResult(
                    status=1,
                    payload=payload,
                    competition=product_offers,
                    final_price=CompareTarget(name=competitor_name, price=target_price),
                    log_message=log_str,
                    offer_id=offer_id,
                    offer_type=offer_type
                )

            # =========================================================================
            # MODE 2: CHỈ GIẢM KHÔNG TĂNG (Smart/Lazy Follow)
            # Logic: Nếu giá đang thấp hơn Target -> Giữ nguyên (Lời hơn).
            #        Nếu giá cao hơn Target -> Giảm xuống.
            # =========================================================================
            elif mode == 2:
                # Case A: Giá hiện tại ĐANG THẤP HƠN hoặc BẰNG giá mục tiêu (tính cả noise)
                # Logic: payload.current_price <= target_price + threshold
                # Nhưng để đơn giản, ta check: Nếu Current < Target thì chắc chắn Skip.

                # Check 1: Nếu giá hiện tại thấp hơn hẳn giá mục tiêu -> SKIP
                if payload.current_price < target_price and self._is_price_diff_significant(payload.current_price,
                                                                                            target_price, payload):
                    # Log kiểu khác để biết là đang giữ giá tốt
                    log_str = get_g2a_log_string("equal", payload, payload.current_price, analysis_result)
                    # Hack nhẹ log message để rõ nghĩa hơn
                    log_str = log_str.replace("đã khớp mục tiêu", "đang thấp hơn mục tiêu (Mode 2 - Giữ giá)")
                    return PayloadResult(status=2, payload=payload, log_message=log_str, offer_id=offer_id)

                # Check 2: Nếu giá xêm xêm nhau (trong vùng noise) -> SKIP
                if not self._is_price_diff_significant(payload.current_price, target_price, payload):
                    log_str = get_g2a_log_string("equal", payload, payload.current_price, analysis_result)
                    return PayloadResult(status=2, payload=payload, log_message=log_str, offer_id=offer_id)

                # Case B: Giá hiện tại CAO HƠN Target -> UPDATE (Undercut)
                log_str = get_g2a_log_string("compare", payload, target_price, analysis_result)
                return PayloadResult(
                    status=1,
                    payload=payload,
                    competition=product_offers,
                    final_price=CompareTarget(name=competitor_name, price=target_price),
                    log_message=log_str,
                    offer_id=offer_id,
                    offer_type=offer_type
                )

            return PayloadResult(status=0, payload=payload, log_message=f"Unknown Mode: {mode}")

        except Exception as e:
            logger.error(f"Error processing payload {payload.product_name}: {e}", exc_info=True)
            return PayloadResult(status=0, payload=payload, log_message=f"Error: {str(e)}", final_price=None)
