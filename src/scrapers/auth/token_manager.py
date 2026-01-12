"""Token management for app authentication."""
import logging
from datetime import datetime, timedelta
from typing import Optional
from cryptography.fernet import Fernet
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.models.database import Credential
from src.models.enums import SourceApp

logger = logging.getLogger(__name__)


class TokenManager:
    """Manages authentication tokens for competitor apps."""

    def __init__(self, session: AsyncSession):
        """Initialize token manager.

        Args:
            session: Database session for credential storage.
        """
        self.session = session
        self._fernet = None
        if settings.encryption_key:
            self._fernet = Fernet(settings.encryption_key.encode())

    def _encrypt(self, value: str) -> str:
        """Encrypt a value.

        Args:
            value: Plain text value.

        Returns:
            Encrypted value.
        """
        if self._fernet:
            return self._fernet.encrypt(value.encode()).decode()
        return value

    def _decrypt(self, value: str) -> str:
        """Decrypt a value.

        Args:
            value: Encrypted value.

        Returns:
            Decrypted plain text.
        """
        if self._fernet:
            return self._fernet.decrypt(value.encode()).decode()
        return value

    async def get_credential(self, source_app: SourceApp) -> Optional[Credential]:
        """Get stored credential for an app.

        Args:
            source_app: Source application.

        Returns:
            Credential or None if not found.
        """
        result = await self.session.execute(
            select(Credential).where(
                Credential.source_app == source_app.value,
                Credential.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def store_credential(
        self,
        source_app: SourceApp,
        username: str,
        password: str,
        device_id: str = None,
    ) -> Credential:
        """Store or update credential for an app.

        Args:
            source_app: Source application.
            username: Account username/phone.
            password: Account password.
            device_id: Optional device ID.

        Returns:
            Stored credential.
        """
        existing = await self.get_credential(source_app)

        encrypted_password = self._encrypt(password)

        if existing:
            existing.username = username
            existing.password_encrypted = encrypted_password
            existing.device_id = device_id
            await self.session.flush()
            return existing
        else:
            credential = Credential(
                source_app=source_app.value,
                username=username,
                password_encrypted=encrypted_password,
                device_id=device_id,
            )
            self.session.add(credential)
            await self.session.flush()
            return credential

    async def store_tokens(
        self,
        source_app: SourceApp,
        access_token: str,
        refresh_token: str = None,
        expires_in_seconds: int = 3600,
        additional_headers: dict = None,
    ) -> None:
        """Store authentication tokens.

        Args:
            source_app: Source application.
            access_token: Access token.
            refresh_token: Optional refresh token.
            expires_in_seconds: Token validity in seconds.
            additional_headers: Any extra headers to store.
        """
        credential = await self.get_credential(source_app)
        if not credential:
            logger.error(f"No credential found for {source_app.value}")
            return

        credential.access_token = access_token
        credential.refresh_token = refresh_token
        credential.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)
        credential.last_login_at = datetime.utcnow()

        if additional_headers:
            credential.additional_headers = additional_headers

        await self.session.flush()
        logger.info(f"Tokens stored for {source_app.value}")

    async def get_access_token(self, source_app: SourceApp) -> Optional[str]:
        """Get current access token.

        Args:
            source_app: Source application.

        Returns:
            Access token or None if not available/expired.
        """
        credential = await self.get_credential(source_app)
        if not credential or not credential.access_token:
            return None

        # Check if expired
        if credential.token_expires_at and credential.token_expires_at < datetime.utcnow():
            logger.warning(f"Token expired for {source_app.value}")
            return None

        return credential.access_token

    async def is_token_valid(self, source_app: SourceApp) -> bool:
        """Check if the stored token is still valid.

        Args:
            source_app: Source application.

        Returns:
            True if token exists and not expired.
        """
        credential = await self.get_credential(source_app)
        if not credential or not credential.access_token:
            return False

        if not credential.token_expires_at:
            return True

        # Add 5 minute buffer
        buffer = timedelta(minutes=5)
        return credential.token_expires_at > (datetime.utcnow() + buffer)

    async def get_password(self, source_app: SourceApp) -> Optional[str]:
        """Get decrypted password for an app.

        Args:
            source_app: Source application.

        Returns:
            Decrypted password or None.
        """
        credential = await self.get_credential(source_app)
        if not credential:
            return None

        return self._decrypt(credential.password_encrypted)

    async def refresh_if_needed(self, source_app: SourceApp) -> bool:
        """Check if token needs refresh and mark for refresh.

        Args:
            source_app: Source application.

        Returns:
            True if refresh is needed.
        """
        is_valid = await self.is_token_valid(source_app)
        return not is_valid
