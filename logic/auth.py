import logging
import time
from typing import Dict, Optional

import httpx

from models.oauth_models import AccessTokenResponse
from utils.config import settings


class AuthHandler:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.token_url = settings.AUTH_URL

        self._auth_payload = {
            "grant_type": "client_credentials",
            "client_id": settings.CLIENT_ID,
            "client_secret": settings.AUTH_SECRET,
        }

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

        self._client = httpx.Client()

    def get_auth_headers(self) -> Dict[str, str]:
        if not self._access_token or time.time() >= self._token_expires_at:
            self.logger.info("Access token is missing or expired. Requesting a new one.")
            self._get_new_token()

        return {"Authorization": f"Bearer {self._access_token}"}

    def _get_new_token(self) -> None:
        self.logger.info("Requesting new token using client credentials...")
        try:
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            response = self._client.post(self.token_url, data=self._auth_payload, headers=headers)

            response.raise_for_status()

            token_data = AccessTokenResponse.model_validate(response.json())

            self._access_token = token_data.access_token
            self._token_expires_at = time.time() + token_data.expires_in - 60

            self.logger.info(
                f"Successfully acquired new access token. It will expire around {time.ctime(self._token_expires_at)}.")

        except httpx.HTTPStatusError as e:
            self.logger.error(
                f"Token request failed with status {e.response.status_code}: {e.response.text}"
            )
            self._access_token = None
            self._token_expires_at = 0.0
            raise ConnectionError("Failed to obtain access token from the authentication server.") from e
        except Exception as e:
            self.logger.error(f"An unexpected error occurred during token request: {e}")
            self._access_token = None
            self._token_expires_at = 0.0
            raise

    def close(self):
        self.logger.info("Closing AuthHandler's HTTP client.")
        self._client.close()
