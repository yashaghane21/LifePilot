from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, EmailStr, Field, StringConstraints

# Stored and compared lowercased: "Yash@Gmail.com" and "yash@gmail.com" are one account.
NormalisedEmail = Annotated[EmailStr, AfterValidator(str.lower)]

# Length is the strongest simple password rule. The upper bound caps hashing work per request.
NewPassword = Annotated[str, Field(min_length=12, max_length=128)]


class RegisterRequest(BaseModel):
    email: NormalisedEmail
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    password: NewPassword


class LoginRequest(BaseModel):
    email: NormalisedEmail
    # No minimum here: login checks the stored hash, it does not enforce today's policy.
    password: Annotated[str, Field(min_length=1, max_length=128)]


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Seconds until the token expires")
