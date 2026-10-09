"""Single-process channel registry; publish memory only after atomic disk commit."""

import json
import os
import tempfile
from pathlib import Path
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field, field_validator

UNCLASSIFIED = "unclassified"
CHANNEL_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class ChannelText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Title cannot be blank")
        return value


class ChannelCreate(ChannelText):
    id: str = Field(min_length=1, max_length=64, pattern=CHANNEL_PATTERN)


class Channel(ChannelCreate):
    enabled: bool = True


class ChannelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None

    @field_validator("title", "description", "enabled")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("Use omission rather than null")
        if isinstance(value, str) and not value.strip():
            # Empty descriptions are allowed; Channel validates titles again.
            return value.strip()
        return value


class ChannelRegistry:
    def __init__(self, path: Path, seeds: dict):
        self.path = path
        self._lock = RLock()
        if path.exists():
            records = json.loads(path.read_text(encoding="utf-8"))
            self._channels = {record["id"]: Channel.model_validate(record).model_dump() for record in records}
            if UNCLASSIFIED not in self._channels or not self._channels[UNCLASSIFIED]["enabled"]:
                raise ValueError("Registry requires enabled unclassified channel")
        else:
            self._channels = {key: Channel(id=key, **value).model_dump() for key, value in seeds.items() if key != UNCLASSIFIED}
            self._channels[UNCLASSIFIED] = Channel(id=UNCLASSIFIED, title="未分类", description="未指定渠道的文章").model_dump()
            self._save(self._channels)

    def _save(self, channels):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, prefix=".channels-", suffix=".tmp", delete=False) as handle:
                temp_path = Path(handle.name)
                json.dump(list(channels.values()), handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def list(self, include_disabled=False):
        with self._lock:
            return [dict(c) for c in self._channels.values() if include_disabled or c["enabled"]]

    def get(self, channel_id):
        with self._lock:
            channel = self._channels.get(channel_id)
            return dict(channel) if channel else None

    def create(self, record):
        channel = Channel.model_validate(record).model_dump()
        with self._lock:
            if channel["id"] in self._channels:
                raise FileExistsError(channel["id"])
            updated = {**self._channels, channel["id"]: channel}
            self._save(updated)
            self._channels = updated
            return dict(channel)

    def update(self, channel_id, changes):
        with self._lock:
            if channel_id not in self._channels:
                raise KeyError(channel_id)
            if channel_id == UNCLASSIFIED and changes.get("enabled") is False:
                raise ValueError("System channel cannot be disabled")
            channel = Channel.model_validate({**self._channels[channel_id], **changes}).model_dump()
            updated = {**self._channels, channel_id: channel}
            self._save(updated)
            self._channels = updated
            return dict(channel)
