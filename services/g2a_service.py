import logging
import re
from typing import List, Optional

from models.g2g_models import Offer, PricingSimulationResponse


def get_prod_id(url: str) -> Optional[int]:
    match = re.search(r'i(\d+)$', url)

    if match:
        return match.group(1)
    else:
        return None


def get_offer_id(url):
    try:
        last_part = url.rstrip('/').split('/')[-1]
        if last_part:
            return last_part
    except IndexError:
        pass
    return None


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

    async def simulate_pricing(
            self,
            product_id: str,
            price: float
    ) -> Optional[PricingSimulationResponse]:
        try:
            logger.info(f"Requesting pricing simulation for product {product_id}.")
            simulation_result = await self.g2a_client.get_pricing_simulation(
                product_id=product_id,
                price=price
            )
            return simulation_result
        except Exception as e:
            logger.error(f"Failed to simulate pricing for product {product_id}: {e}")
            return None
