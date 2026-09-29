"""Spec §13/§55: email notification channel - the one this codebase's own
notifications/models.py docstring flagged as a documented future extension
("Email/SMS/push channels are... not implemented here since there's no
reachable provider to verify against in this sandbox"). Built this session
following the exact same shape as payments/providers/base.py: one abstract
interface, a fully-testable Mock implementation, and a real implementation
that's written-but-not-live-tested."""
import abc
from dataclasses import dataclass


@dataclass
class EmailSendResult:
    provider: str
    accepted: bool  # False means the provider itself rejected it (e.g. bad address) - not a network error, which raises instead


class EmailProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    async def send(self, to: str, subject: str, body_text: str) -> EmailSendResult: ...
