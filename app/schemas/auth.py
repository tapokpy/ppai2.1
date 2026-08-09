from pydantic import BaseModel


class GenerateOTTRequest(BaseModel):
    telegram_id: int


class GenerateOTTResponse(BaseModel):
    ott: str
    expires_in: int


class SSORequest(BaseModel):
    ott: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
