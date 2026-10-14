"""AI-driven passage selection. The model only chooses a reference, never the text."""

import logging
from collections.abc import Sequence
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

    def __init__(self, api_key: str, model: str, *, client: Any | None = None) -> None:
        self._model = model
        self._client = client or genai.Client(api_key=api_key)

    def choose(
        self,
        recent: Sequence[HistoryEntry],
        focus_group: str,
        rejected: Sequence[str],
    ) -> PassageReference:
        prompt = build_prompt(recent, focus_group, rejected)
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=PassageChoice,
                    temperature=1.0,
                ),
            )
        except (genai_errors.APIError, httpx.HTTPError) as exc:
            raise SelectionError(f"Gemini request failed: {type(exc).__name__}: {exc}") from exc

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
