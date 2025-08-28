import asyncio
import logging
from datetime import datetime
from time import sleep

from clients.g2g_client import G2aClient
from logic.auth import AuthHandler
from logic.processor import G2AProcessor

from clients.google_sheets_client import GoogleSheetsClient
from services.analyze_g2a_competition import CompetitionAnalysisService
from services.g2a_service import G2AService, get_offer_id
from services.sheet_service import SheetService
from utils.config import settings


async def run_automation():
    auth_handler = None
    g2a_client = None
    try:
        g_client = GoogleSheetsClient(settings.GOOGLE_KEY_PATH)
        sheet_service = SheetService(client=g_client)

        auth_handler = AuthHandler()
        g2a_client = G2aClient(auth_handler=auth_handler)
        g2a_service = G2AService(g2a_client=g2a_client)
        analysis_service = CompetitionAnalysisService()
        processor = G2AProcessor(g2a_service=g2a_service, analysis_service=analysis_service)

        payloads_to_process = sheet_service.get_payloads_to_process()

        if not payloads_to_process:
            logging.info("No payloads to process.")
            return

        for payload in payloads_to_process:
            try:
                hydrated_payload = sheet_service.fetch_data_for_payload(payload)

                result = await processor.process_single_payload(hydrated_payload)

                log_data = None
                if result.status == 1 and result.final_price is not None:
                    # TODO: Implement a real update_product_price method in G2aService
                    offer_id = get_offer_id(payload.product_id)
                    await processor.g2a_service.update_product_price(offer_id=offer_id, new_price=result.final_price.price)
                    logging.info(
                        f"SUCCESS: Processed {payload.product_name}. New price: {result.final_price.price:.3f}. Competitor: {result.final_price.name}"
                    )
                    log_data = {
                        'note': result.log_message,
                        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                else:
                    logging.warning(f"SKIPPED: {payload.product_name}. Reason: {result.log_message.splitlines()[0]}")
                    log_data = {
                        'note': result.log_message,
                        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }

                if log_data:
                    sheet_service.update_log_for_payload(payload, log_data)

                logging.info(f"Processed row {payload.row_index}, sleeping for {settings.SLEEP_TIME}s.")
                sleep(settings.SLEEP_TIME)

            except Exception as e:
                logging.error(f"Error in flow for row {payload.row_index}: {e}", exc_info=True)
                sheet_service.update_log_for_payload(payload, {'note': f"Error: {e}"})

    except Exception as e:
        logging.critical(f"A critical error occurred, stopping the program: {e}", exc_info=True)
    finally:
        if auth_handler:
            await auth_handler.close()
        if g2a_client:
            await g2a_client.close()
        logging.info("Cleaned up resources.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)

    while True:
        asyncio.run(run_automation())
        logging.info("Completed processing all payloads. Next round in 10 seconds.")
        sleep(10)
