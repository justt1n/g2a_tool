import logging
from typing import Any, Dict, Optional

from clients.base_rest_client import BaseRestAPIClient
from logic.auth import AuthHandler
from models.g2g_models import OffersResponse, PricingSimulationResponse

logger = logging.getLogger(__name__)


class G2aClient(BaseRestAPIClient):
    def __init__(self, auth_handler: AuthHandler):
        super().__init__(base_url="https://api.g2a.com")
        self.auth_handler = auth_handler
        logger.info("G2aClient initialized (No-Base-Change version).")

    async def close(self):
        await self.auth_handler.close()
        await super().close()

    async def _prepare_payload(self, **kwargs: Any) -> Dict[str, Any]:
        return kwargs

    async def get(self,
                  endpoint: str,
                  response_model,
                  params: Optional[Dict[str, Any]] = None,
                  auth_required: bool = False
                  ) -> Any:

        if not auth_required:
            response = await self._make_request(method='GET', endpoint=endpoint, params=params)
            return response_model.model_validate(response.json())

        original_headers = self._client.headers.copy()
        try:
            auth_headers = await self.auth_handler.get_auth_headers()

            self._client.headers.update(auth_headers)

            response = await self._make_request(method='GET', endpoint=endpoint, params=params)
            return response_model.model_validate(response.json())

        finally:
            self._client.headers = original_headers

    async def get_product_offers(
            self,
            product_id: str,
            country_code: str,
            visibility: str = "all"
    ) -> OffersResponse:
        logger.info(f"Fetching offers for product {product_id} in country {country_code}")

        endpoint = f"/v3/products/{product_id}/offers"
        params = {
            "visibility": visibility,
            "countryCode": country_code,
        }

        return await self.get(
            endpoint=endpoint,
            response_model=OffersResponse,
            params=params,
            auth_required=True
        )

    async def get_pricing_simulation(
            self,
            product_id: str,
            price: float
    ) -> PricingSimulationResponse:
        logger.info(f"Simulating pricing for product {product_id} at price {price}")

        endpoint = "/v3/pricing/simulations"
        params = {
            "productId": product_id,
            "price": str(price)
        }

        return await self.get(
            endpoint=endpoint,
            response_model=PricingSimulationResponse,
            params=params,
            auth_required=True
        )
