"""Remote provider backed by the ABíbliaDigital community API."""

import logging

import httpx
from pydantic import BaseModel, ValidationError

from palavra_do_dia.books import Book
from palavra_do_dia.errors import InvalidReferenceError, ProviderUnavailableError

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://abibliadigital.api.br/api"
USER_AGENT = "palavra-do-dia/0.1"


class _ApiVerse(BaseModel):
    number: int
    text: str


class _ApiChapter(BaseModel):
    verses: list[_ApiVerse]


class AbibliaDigitalProvider:
    """Fetches whole chapters from ``abibliadigital.api.br``.

    The API has no verse-range endpoint, so chapters are fetched and sliced locally.
    """

    def __init__(
        self,
        translation: str = "nvi",
        *,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.Client | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._translation = translation.lower()
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            transport=httpx.HTTPTransport(retries=2),
        )

    @property
    def version(self) -> str:
        return self._translation.upper()

    def get_chapter(self, book: Book, chapter: int) -> list[str]:
        url = f"{self._base_url}/verses/{self._translation}/{book.abbrev}/{chapter}"
        try:
            response = self._client.get(url)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"ABíbliaDigital unreachable: {type(exc).__name__}"
            ) from exc

        if response.status_code == httpx.codes.NOT_FOUND and self._is_api_not_found(response):
            raise InvalidReferenceError(f"{book.name} {chapter} does not exist")
        if response.is_error:
            raise ProviderUnavailableError(f"ABíbliaDigital returned HTTP {response.status_code}")

        return self._parse_verses(response)

    @staticmethod
    def _is_api_not_found(response: httpx.Response) -> bool:
        """The API answers missing chapters with ``{"msg": ...}``; any other 404 is infra."""
        try:
            body = response.json()
        except ValueError:
            return False
        return isinstance(body, dict) and "msg" in body

    @staticmethod
    def _parse_verses(response: httpx.Response) -> list[str]:
        try:
            payload = _ApiChapter.model_validate_json(response.content)
        except ValidationError as exc:
            raise ProviderUnavailableError("ABíbliaDigital returned a malformed payload") from exc

        verses = sorted(payload.verses, key=lambda verse: verse.number)
        if [verse.number for verse in verses] != list(range(1, len(verses) + 1)):
            raise ProviderUnavailableError("ABíbliaDigital returned non-contiguous verses")
        return [verse.text.strip() for verse in verses]
