from pydantic import BaseModel, EmailStr, Field


class PasswordLoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    nickname: str | None = None


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class UpdateProfileRequest(BaseModel):
    # 仅传需要改的字段；None = 不改。昵称 1–50 字符（strip 后再校验长度在路由里做）。
    nickname: str | None = Field(default=None, max_length=80)


class UploadAvatarRequest(BaseModel):
    # base64 data URL：data:image/png;base64,<payload>（前端 FileReader.readAsDataURL 直出）。
    image: str = Field(min_length=1, max_length=3_500_000)


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


class IdentitySummaryDTO(BaseModel):
    provider: str
    email: str | None = None
    phone: str | None = None


class CurrentUserDTO(BaseModel):
    id: str
    nickname: str | None = None
    avatar_url: str | None = None
    is_admin: bool = False
    can_create: bool = False
    identities: list[IdentitySummaryDTO]
