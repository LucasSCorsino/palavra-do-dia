"""AI-driven passage selection. The model only chooses a reference, never the text."""

import logging
import time
from collections.abc import Callable, Sequence
from typing import Any, Protocol

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

from palavra_do_dia.books import catalog_for_prompt
from palavra_do_dia.errors import InvalidReferenceError, SelectionError
from palavra_do_dia.models import MAX_VERSES_PER_PASSAGE, HistoryEntry, PassageReference

logger = logging.getLogger(__name__)

# Seconds to wait before each retry of the same model (so 4 tries in total).
RETRY_DELAYS: tuple[float, ...] = (5.0, 15.0, 30.0)


def _is_transient(exc: Exception) -> bool:
    """Overload / rate limit / server / network errors are worth retrying; 4xx are not."""
    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        return code in (429, 500, 502, 503, 504)
    return isinstance(exc, httpx.HTTPError)


class ReferenceSelector(Protocol):
    def choose(
        self,
        recent: Sequence[HistoryEntry],
        focus_group: str,
        rejected: Sequence[str],
    ) -> PassageReference:
        """Pick a passage from ``focus_group`` that is not in ``recent`` or ``rejected``."""
        ...


class PassageChoice(BaseModel):
    """Structured-output schema sent to Gemini. Validation happens afterwards."""

    book: str
    chapter: int
    verse_start: int
    verse_end: int


def build_prompt(
    recent: Sequence[HistoryEntry],
    focus_group: str,
    rejected: Sequence[str],
) -> str:
    recent_labels = ", ".join(entry.reference.label for entry in recent) or "nenhuma"
    rejected_block = (
        "\nEscolhas anteriores REJEITADAS nesta execução (não repita): " + "; ".join(rejected)
        if rejected
        else ""
    )
    return (
        "Você escolhe a 'Palavra do Dia' para um leitor cristão.\n"
        f"Escolha UMA passagem de 1 a {MAX_VERSES_PER_PASSAGE} versículos consecutivos, "
        "dentro de um único capítulo.\n"
        "Regras:\n"
        "- A passagem deve fazer sentido completo sozinha: não comece nem termine no meio de "
        "uma ideia; inclua os versículos necessários para a mensagem ficar compreensível.\n"
        "- Prefira passagens edificantes e de aplicação prática (encorajamento, sabedoria, "
        "esperança, gratidão, arrependimento, ensino).\n"
        f"- Foco desta escolha: livros do grupo «{focus_group}».\n"
        "- Evite os trechos mais populares e repetidos; varie livros e temas.\n"
        f"- NÃO repita nem sobreponha estas passagens recentes: {recent_labels}.\n"
        f"- Use SOMENTE estas abreviações de livro (abreviação=nome): {catalog_for_prompt()}.\n"
        "- Informe apenas a referência. Não escreva o texto bíblico."
        f"{rejected_block}"
    )


class GeminiSelector:
    """Selects a passage reference using Gemini with schema-constrained JSON output."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        retry_delays: Sequence[float] = RETRY_DELAYS,
    ) -> None:
        # ``model`` may be a comma-separated fallback chain: "primary,backup".
        self._models = [name.strip() for name in model.split(",") if name.strip()]
        self._client = client or genai.Client(api_key=api_key)
        self._sleep = sleep
        self._retry_delays = tuple(retry_delays)

    def _generate(self, prompt: str) -> Any:
        last_exc: Exception | None = None
        for model in self._models:
            for attempt in range(len(self._retry_delays) + 1):
                try:
                    return self._client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=PassageChoice,
                            temperature=1.0,
                        ),
                    )
                except (genai_errors.APIError, httpx.HTTPError) as exc:
                    last_exc = exc
                    if not _is_transient(exc):
                        raise SelectionError(
                            f"Gemini request failed: {type(exc).__name__}: {exc}"
                        ) from exc
                    logger.warning(
                        "Gemini %s transient failure (try %d): %s", model, attempt + 1, exc
                    )
                    if attempt < len(self._retry_delays):
                        self._sleep(self._retry_delays[attempt])
            logger.warning("Giving up on model %s; trying next fallback if any.", model)
        raise SelectionError(
            f"Gemini request failed: {type(last_exc).__name__}: {last_exc}"
        ) from last_exc

    def choose(
        self,
        recent: Sequence[HistoryEntry],
        focus_group: str,
        rejected: Sequence[str],
    ) -> PassageReference:
        prompt = build_prompt(recent, focus_group, rejected)
        response = self._generate(prompt)

        choice = self._parse_choice(response)
        try:
            return PassageReference(**choice.model_dump())
        except ValidationError as exc:
            details = "; ".join(error["msg"] for error in exc.errors())
            raise InvalidReferenceError(f"AI returned an invalid reference: {details}") from exc

    @staticmethod
    def _parse_choice(response: Any) -> PassageChoice:
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, PassageChoice):
            return parsed
        try:
            return PassageChoice.model_validate_json(getattr(response, "text", None) or "")
        except ValidationError as exc:
            raise SelectionError("Gemini returned an unparsable response") from exc
