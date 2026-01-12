"""Device fingerprint generator for anti-detection."""
import random
import uuid
import hashlib
from typing import Dict
from dataclasses import dataclass


@dataclass
class DeviceProfile:
    """Represents a mobile device profile."""
    device_model: str
    brand: str
    android_version: str


class DeviceFingerprint:
    """Generate realistic device fingerprints to avoid detection."""

    # Common Android devices in Egypt
    DEVICE_PROFILES = [
        DeviceProfile("Samsung SM-A525F", "samsung", "13"),
        DeviceProfile("Samsung SM-A536B", "samsung", "14"),
        DeviceProfile("Samsung SM-A546B", "samsung", "14"),
        DeviceProfile("Xiaomi Redmi Note 12", "Xiaomi", "13"),
        DeviceProfile("Xiaomi Redmi Note 11", "Xiaomi", "12"),
        DeviceProfile("Xiaomi Redmi 12", "Xiaomi", "13"),
        DeviceProfile("OPPO A96", "OPPO", "12"),
        DeviceProfile("OPPO A78", "OPPO", "13"),
        DeviceProfile("realme 9 Pro", "realme", "13"),
        DeviceProfile("realme 10", "realme", "13"),
        DeviceProfile("Huawei nova 9", "HUAWEI", "11"),
        DeviceProfile("Infinix Note 12", "Infinix", "12"),
        DeviceProfile("Infinix Hot 30", "Infinix", "13"),
        DeviceProfile("TECNO Spark 10", "TECNO", "13"),
    ]

    SCREEN_RESOLUTIONS = [
        (1080, 2400, 420),  # Most common
        (1080, 2340, 400),
        (720, 1600, 320),
        (1080, 2408, 440),
        (1080, 2460, 450),
    ]

    def __init__(self, source_app: str, device_id: str = None):
        """Initialize device fingerprint.

        Args:
            source_app: The app this fingerprint is for.
            device_id: Optional fixed device ID. If None, generates one.
        """
        self.source_app = source_app
        self._device_id = device_id or self._generate_device_id()
        self._current_profile = random.choice(self.DEVICE_PROFILES)
        self._screen = random.choice(self.SCREEN_RESOLUTIONS)
        self._app_version = "1.0.0"  # Update after API discovery

    def _generate_device_id(self) -> str:
        """Generate a realistic Android device ID."""
        return hashlib.md5(uuid.uuid4().bytes).hexdigest()[:16]

    @property
    def device_id(self) -> str:
        """Get the device ID."""
        return self._device_id

    def set_device_id(self, device_id: str) -> None:
        """Set device ID from stored credentials.

        Args:
            device_id: The device ID to use.
        """
        self._device_id = device_id

    def set_app_version(self, version: str) -> None:
        """Set the app version.

        Args:
            version: App version string.
        """
        self._app_version = version

    def get_user_agent(self) -> str:
        """Generate User-Agent string for the app."""
        profile = self._current_profile

        # Format varies by app - adjust based on API discovery
        if self.source_app == "tager_elsaada":
            return (
                f"TagerElsaada/{self._app_version} "
                f"(Linux; Android {profile.android_version}; {profile.device_model}) "
                f"okhttp/4.11.0"
            )
        elif self.source_app == "ben_soliman":
            return (
                f"BenSoliman/{self._app_version} "
                f"(Linux; Android {profile.android_version}; {profile.device_model}) "
                f"okhttp/4.10.0"
            )
        else:
            return (
                f"MobileApp/{self._app_version} "
                f"(Linux; Android {profile.android_version}; {profile.device_model}) "
                f"okhttp/4.11.0"
            )

    def get_headers(self) -> Dict[str, str]:
        """Get all device-related headers."""
        profile = self._current_profile
        width, height, dpi = self._screen

        headers = {
            "User-Agent": self.get_user_agent(),
            "Accept": "application/json",
            "Accept-Language": "ar-EG,ar;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "X-Device-Id": self._device_id,
            "X-Device-Model": profile.device_model,
            "X-Device-Brand": profile.brand,
            "X-Android-Version": profile.android_version,
            "X-Screen-Density": str(dpi),
            "X-Screen-Resolution": f"{width}x{height}",
            "X-App-Version": self._app_version,
            "X-Platform": "android",
        }

        return headers

    def rotate_profile(self) -> None:
        """Rotate to a different device profile."""
        self._current_profile = random.choice(self.DEVICE_PROFILES)
        self._screen = random.choice(self.SCREEN_RESOLUTIONS)

    def get_profile_info(self) -> Dict[str, str]:
        """Get current profile information for logging."""
        return {
            "device_model": self._current_profile.device_model,
            "brand": self._current_profile.brand,
            "android_version": self._current_profile.android_version,
            "device_id": self._device_id,
        }
