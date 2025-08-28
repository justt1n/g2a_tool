import asyncio
import logging

from clients.g2g_client import G2aClient
from logic.auth import AuthHandler
from services.g2a_service import G2AService


async def test_auth():
    auth_handler = AuthHandler()
    try:
        headers = await auth_handler.get_auth_headers()
        logging.info(f"Obtained headers: {headers}")
    except Exception as e:
        logging.error(f"Error obtaining auth headers: {e}")
    finally:
        await auth_handler.close()


async def test_get_compare_price():
    auth_handler = AuthHandler()

    g2a_client = G2aClient(auth_handler=auth_handler)

    async with g2a_client:
        try:
            product_id = "10000070179155"
            country_code = "EN"

            offers_response = await g2a_client.get_product_offers(
                product_id=product_id,
                country_code=country_code
            )

            print(f"Found {offers_response.meta.total_results} offers for product {product_id}.")
            for offer in offers_response.data:
                print(f"- Seller: {offer.seller.name}, "
                      f"Price: {offer.price.retail.final[0].value} {offer.price.retail.final[0].currency_code}, "
                      f"Rating: {offer.seller.rating}%")

        except Exception as e:
            logging.error(f"An error occurred: {e}", exc_info=True)


async def test_get_compare_service():
    auth_handler = AuthHandler()
    g2a_client = G2aClient(auth_handler=auth_handler)

    async with g2a_client:
        try:
            g2a_service = G2AService(g2a_client=g2a_client)

            out_len_product_id = "1000007017915235"
            product_id = "10000070179155"
            no_offers_product_id = "99900070179129"
            country_code = "DE"

            try:
                offers = await g2a_service.get_compare_price(prod_id=int(no_offers_product_id), country=country_code)
            except ConnectionError as e:
                logging.error(f"Connection error while fetching offers: {e}")
                return
            print(f"Found {len(offers)} offers for product {product_id}.")
            for offer in offers:
                print(f"- Seller: {offer.seller.name}, "
                      f"Price: {offer.price.retail.final[0].value} {offer.price.retail.final[0].currency_code}, "
                      f"Rating: {offer.seller.rating}%")

        except Exception as e:
            logging.error(f"An error occurred: {e}", exc_info=True)


async def test_get_offer_detail():
    auth_handler = AuthHandler()
    g2a_client = G2aClient(auth_handler=auth_handler)
    g2a_service = G2AService(g2a_client=g2a_client)

    try:
        offer_id_to_check = "a93f5a5f-63d2-4a15-abe0-025adf3bec34"

        offer_type = await g2a_service.get_offer_type(offer_id=offer_id_to_check)

        if offer_type:
            print(f"Successfully retrieved offer type for ID {offer_id_to_check}.")
            print(f"Offer Type is: '{offer_type}'")  # Kết quả sẽ là: 'game'
        else:
            print(f"Failed to get type for offer ID {offer_id_to_check}.")

    finally:
        await g2a_client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_get_offer_detail())
