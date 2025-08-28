import asyncio
import logging
from datetime import datetime
from time import sleep

from clients.google_sheets_client import GoogleSheetsClient
from services.sheet_service import SheetService
from utils.config import settings


async def run_automation():
    try:
        g_client = GoogleSheetsClient(settings.GOOGLE_KEY_PATH)
        sheet_service = SheetService(client=g_client)
        payloads_to_process = sheet_service.get_payloads_to_process()
        # TODO Initialize G2aClient and G2aService here
        # g2a_client = G2aClient()
        # processor = Processor(g2a_service=G2aService(g2a_client=g2a_client))

        if not payloads_to_process:
            logging.info("No payloads to process.")
            return

        for payload in payloads_to_process:
            try:
                hydrated_payload = sheet_service.fetch_data_for_payload(payload)
                # result = processor.process_single_payload(hydrated_payload)
                # if result.status == 1:
                #     #TODO: Update price on Eneba
                #     processor.g2a_service.update_product_price(offer_id=payload.offer_id,
                #     new_price=result.final_price.price)
                #     logging.info(
                #         f"Successfully processed payload for {payload.product_name}. Final price: {
                #         result.final_price.price:.3f}")
                #     log_data = {
                #         'note': result.log_message,
                #         'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                #     }
                # else:
                #     logging.warning(f"Payload {payload.product_name} did not meet conditions for processing.")
                #     log_data = {
                #         'note': result.log_message,
                #         'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                #     }
                logging.warning(f"Payload {payload.product_name} did not meet conditions for processing.")
                log_data = {
                    'note': f"{payload.model_dump_json()}",
                    'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }

                if log_data:
                    sheet_service.update_log_for_payload(payload, log_data)

                logging.info(f"Processed row {payload.row_index}, sleeping for {settings.SLEEP_TIME}s.")
                sleep(settings.SLEEP_TIME)

            except Exception as e:
                logging.error(f"Error in flow for row {payload.row_index}: {e}")
                sheet_service.update_log_for_payload(payload, {'note': f"Error: {e}"})

    except Exception as e:
        logging.critical(f"Đã xảy ra lỗi nghiêm trọng, chương trình dừng lại: {e}", exc_info=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)

    while True:
        asyncio.run(run_automation())
        logging.info("Completed processing all payloads. Next round in 10 seconds.")
        sleep(10)
