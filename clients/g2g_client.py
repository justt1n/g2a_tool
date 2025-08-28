import logging
from typing import Any, Dict, Optional

from httpx import Response

from clients.base_rest_client import BaseRestAPIClient
from logic.auth import AuthHandler
from models.g2g_models import OffersResponse, OfferDetailsResponse, UpdateOfferPayload

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

    async def patch(self,
                    endpoint: str,
                    json_data: Optional[Dict[str, Any]] = None,
                    auth_required: bool = False
                    ) -> Response:
        if not auth_required:
            response = await self._make_request(method='PATCH', endpoint=endpoint, json_data=json_data)
            return response

        original_headers = self._client.headers.copy()
        try:
            auth_headers = await self.auth_handler.get_auth_headers()
            self._client.headers.update(auth_headers)
            response = await self._make_request(method='PATCH', endpoint=endpoint, json_data=json_data)
            return response
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

    async def get_offer_details(self, offer_id: str) -> OfferDetailsResponse:
        logger.info(f"Fetching details for offer {offer_id}")

        endpoint = f"/v3/sales/offers/{offer_id}"

        return await self.get(
            endpoint=endpoint,
            response_model=OfferDetailsResponse,
            auth_required=True
        )

    async def patch_offer_details(self, offer_id: str, payload: UpdateOfferPayload) -> Response:
        logger.info(f"Patching details for offer {offer_id}")
        endpoint = f"/v3/sales/offers/{offer_id}"

        return await self.patch(
            endpoint=endpoint,
            json_data=payload.model_dump(by_alias=True, exclude_none=True),
            auth_required=True
        )
