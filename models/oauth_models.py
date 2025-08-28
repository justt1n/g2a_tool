from pydantic import BaseModel


class AccessTokenResponse(BaseModel):
    access_token: str
    expires_in: int
    token_type: str
