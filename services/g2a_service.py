import logging
from typing import List, Optional, Dict, Any

from models.g2g_models import Offer, UpdatePricePayload, UpdateInventoryPayload, UpdateOfferVariantPayload, \
    UpdateOfferPayload, OfferDetailsResponse

logger = logging.getLogger(__name__)


class G2AService:

    def __init__(self, g2a_client):
        self.g2a_client = g2a_client

    async def get_compare_price(self, prod_id: int, country: str = "DE") -> List[Offer]:
        try:
            logger.info(f"Fetching G2A offers for product ID {prod_id} in country {country}.")
            offers_response = await self.g2a_client.get_product_offers(
                product_id=str(prod_id),
                country_code=country
            )
            return offers_response.get_offers()

        except ConnectionError as e:
            logger.error(f"Connection error fetching G2A offers for {prod_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching G2A offers for {prod_id}: {e}")
            return []

    async def update_product_price(self, offer_id: str, new_price: float) -> bool:
        logger.info(f"Updating G2A offer {offer_id} with price {new_price}...")
        return True

    async def get_offer_type(self, offer_id: str) -> Optional[str]:
        try:
            logger.info(f"Requesting type for offer {offer_id}.")

            response = await self.g2a_client.get_offer_details(offer_id)

            if response and response.data:
                return response.data.type

            return None
        except Exception as e:
            logger.error(f"Failed to get type for offer {offer_id}: {e}")
            return None

    async def update_offer_price(
            self,
            offer_id: str,
            offer_type: str,
            new_price: float,
            stock: Optional[int] = None
    ) -> bool:
        logger.info(f"Preparing to update price for offer {offer_id} (type: {offer_type})")

        try:
            price_payload = UpdatePricePayload(retail=f"{new_price:.2f}")
            variant_data: Dict[str, Any] = {"price": price_payload}

            if offer_type == "dropshipping" and stock is not None:
                variant_data["inventory"] = UpdateInventoryPayload(size=stock)

            variant_payload = UpdateOfferVariantPayload(**variant_data)

            final_payload = UpdateOfferPayload(
                offerType=offer_type,
                variant=variant_payload
            )

            await self.g2a_client.patch_offer_details(
                offer_id,
                payload=final_payload
            )

            logger.info(f"Successfully updated price for offer {offer_id}.")
            return True

        except Exception as e:
            logger.error(f"Failed to update price for offer {offer_id}: {e}")
            return False

    async def get_offer_details_full(self, offer_id: str) -> Optional[OfferDetailsResponse]:
        try:
            # logger.info(f"Fetching full details for offer {offer_id}")
            return await self.g2a_client.get_offer_details(offer_id)
        except Exception as e:
            logger.error(f"Failed to get details for offer {offer_id}: {e}")
            return None
