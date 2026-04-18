from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent.profiles import runtime_profile_to_dict
from app.core.settings import Settings
from app.db.repositories.runtime_profiles import (
    activate_profile,
    get_active_profile,
    get_default_profile,
    list_profiles,
    seed_builtin_profiles,
    set_default_profile,
)


class RuntimeProfileService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def ensure_seeded(self) -> None:
        seed_builtin_profiles(self.db, self.settings)

    def list_payload(self) -> dict:
        profiles = list_profiles(self.db)
        active = get_active_profile(self.db)
        default = get_default_profile(self.db)
        return {
            "active_profile_id": active.profile_id if active else None,
            "default_profile_id": default.profile_id if default else None,
            "profiles": [runtime_profile_to_dict(profile) for profile in profiles],
        }

    def activate(self, profile_id: str) -> dict | None:
        profile = activate_profile(self.db, profile_id)
        if not profile:
            return None
        return runtime_profile_to_dict(profile)

    def set_default(self, profile_id: str) -> dict | None:
        profile = set_default_profile(self.db, profile_id)
        if not profile:
            return None
        return runtime_profile_to_dict(profile)

