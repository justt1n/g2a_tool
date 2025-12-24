import asyncio
import logging
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

from clients.g2g_client import G2aClient
from clients.google_sheets_client import GoogleSheetsClient
from logic.auth import AuthHandler
from logic.processor import G2AProcessor
from services.analyze_g2a_competition import CompetitionAnalysisService
from services.g2a_service import G2AService
from services.sheet_service import SheetService
from utils.config import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("googleapiclient").setLevel(logging.WARNING)

CONCURRENT_WORKERS = getattr(settings, 'WORKERS', 1)


async def process_row_wrapper(
        payload,
        sheet_service: SheetService,
        processor: G2AProcessor,
        g2a_service: G2AService,
        worker_semaphore: asyncio.Semaphore,
        google_sheets_lock: asyncio.Semaphore  # <--- THÊM BIẾN NÀY
) -> Optional[Tuple[Any, Dict[str, Any]]]:
    """
    Worker xử lý 1 hàng.
    """
    try:
        logging.info(f"Start processing row {payload.row_index} ({payload.product_name})...")

        # --- BƯỚC 1: LẤY DỮ LIỆU (CÓ LOCK) ---
        # Bắt buộc phải Lock đoạn này vì thư viện Google cũ không hỗ trợ đọc song song
        async with google_sheets_lock:
            hydrated_payload = await asyncio.to_thread(
                sheet_service.fetch_data_for_payload, payload
            )

        # --- BƯỚC 2: XỬ LÝ LOGIC (SONG SONG - KHÔNG CẦN LOCK) ---
        result = await processor.process_single_payload(hydrated_payload)
        log_data = None

        # --- BƯỚC 3: CẬP NHẬT GIÁ (SONG SONG) ---
        if result.status == 1 and result.final_price is not None and result.offer_id and result.offer_type:
            update_successful = await g2a_service.update_offer_price(
                offer_id=result.offer_id,
                offer_type=result.offer_type,
                new_price=result.final_price.price,
                stock=hydrated_payload.fetched_stock
            )

            if update_successful:
                logging.info(f"SUCCESS: Updated {payload.product_name} -> {result.final_price.price:.3f}")
                log_data = {
                    'note': result.log_message,
                    'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            else:
                logging.error(f"FAILED API Update: {payload.product_name}")
                log_data = {
                    'note': f"{result.log_message}\n\nERROR: API update call failed.",
                    'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
        else:
            # Logic skip
            log_data = {
                'note': result.log_message,
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

        # --- BƯỚC 4: TRẢ VỀ KẾT QUẢ ĐỂ GHI SAU ---
        if log_data:
            return (payload, log_data)
        return None

    except Exception as e:
        logging.error(f"Error processing row {payload.row_index}: {e}", exc_info=True)
        return (payload, {'note': f"Error: {e}"})

    finally:
        worker_semaphore.release()


async def run_automation(
        sheet_service: SheetService,
        processor: G2AProcessor,
        g2a_service: G2AService,
        google_sheets_lock: asyncio.Semaphore
):
    worker_semaphore = asyncio.Semaphore(CONCURRENT_WORKERS)
    tasks = []

    try:
        logging.info("Fetching payloads from Google Sheets...")

        # Lấy danh sách row (Chạy 1 lần đầu, không cần lock)
        payloads_to_process = await asyncio.to_thread(
            sheet_service.get_payloads_to_process
        )

        if not payloads_to_process:
            logging.info("No payloads to process.")
            return

        logging.info(f"Found {len(payloads_to_process)} payloads. Start processing...")

        for payload in payloads_to_process:
            await worker_semaphore.acquire()
            task = asyncio.create_task(
                process_row_wrapper(
                    payload=payload,
                    sheet_service=sheet_service,
                    processor=processor,
                    g2a_service=g2a_service,
                    worker_semaphore=worker_semaphore,
                    google_sheets_lock=google_sheets_lock  # <--- TRUYỀN LOCK VÀO
                )
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # --- GIAI ĐOẠN GHI LOG (BATCH UPDATE) ---
        updates_to_push = [res for res in results if res is not None]

        if updates_to_push:
            logging.info(f"Processing complete. Saving logs for {len(updates_to_push)} rows...")
            # Gọi hàm batch update (Đã viết ở bước trước)
            await asyncio.to_thread(
                sheet_service.batch_update_logs, updates_to_push
            )
        else:
            logging.info("Processing complete. No logs to update.")

    except Exception as e:
        logging.critical(f"Error in run_automation: {e}", exc_info=True)


async def main():
    google_sheets_lock = asyncio.Semaphore(1)

    auth_handler = None
    g2a_client = None

    try:
        logging.info("Initializing services...")
        g_client = GoogleSheetsClient(settings.GOOGLE_KEY_PATH)
        sheet_service = SheetService(client=g_client)

        auth_handler = AuthHandler()
        g2a_client = G2aClient(auth_handler=auth_handler)
        g2a_service = G2AService(g2a_client=g2a_client)

        analysis_service = CompetitionAnalysisService()
        processor = G2AProcessor(g2a_service=g2a_service, analysis_service=analysis_service)

        logging.info("Services ready.")

        while True:
            try:
                logging.info("===== NEW ROUND =====")

                await run_automation(
                    sheet_service=sheet_service,
                    processor=processor,
                    g2a_service=g2a_service,
                    google_sheets_lock=google_sheets_lock
                )

                logging.info(f"Round finished. Sleep {settings.SLEEP_TIME}s.")
                await asyncio.sleep(settings.SLEEP_TIME)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.critical(f"Error in main loop: {e}. Retry in 30s.", exc_info=True)
                await asyncio.sleep(30)

    finally:
        if auth_handler:
            await auth_handler.close()
        if g2a_client:
            await g2a_client.close()


if __name__ == "__main__":
    try:
        # asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
