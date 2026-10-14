from pathlib import Path

import httpx
import pytest
import respx

from palavra_do_dia.bible import AbibliaDigitalProvider, BibleService, LocalBibleProvider
from palavra_do_dia.books import get_book
from palavra_do_dia.errors import (
    AllProvidersFailedError,
    InvalidReferenceError,
    ProviderUnavailableError,
)
from tests.conftest import FakeProvider, make_ref

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "almeida1911.json"
JOAO = get_book("jo")
assert JOAO is not None
URL = "https://abibliadigital.api.br/api/verses/nvi/jo/3"


def _api_payload(count: int) -> dict[str, object]:
    return {
        "book": {"abbrev": {"pt": "jo"}},
        "chapter": {"number": 3, "verses": count},
        "verses": [{"number": n, "text": f"  texto {n} "} for n in range(1, count + 1)],
    }


# --- remote provider ---------------------------------------------------------------------


@respx.mock
def test_remote_returns_trimmed_verses_in_order() -> None:
    payload = _api_payload(3)
    payload["verses"] = list(reversed(payload["verses"]))  # type: ignore[call-overload]
    respx.get(URL).mock(return_value=httpx.Response(200, json=payload))

    verses = AbibliaDigitalProvider("nvi", client=httpx.Client()).get_chapter(JOAO, 3)

    assert verses == ["texto 1", "texto 2", "texto 3"]


@respx.mock
def test_remote_404_means_invalid_reference() -> None:
    respx.get(URL).mock(return_value=httpx.Response(404, json={"msg": "Chapter not found"}))

    with pytest.raises(InvalidReferenceError):
        AbibliaDigitalProvider("nvi", client=httpx.Client()).get_chapter(JOAO, 3)


@respx.mock
def test_remote_infrastructure_404_is_unavailable_not_invalid() -> None:
    respx.get(URL).mock(return_value=httpx.Response(404, text="<html>Not Found</html>"))

    with pytest.raises(ProviderUnavailableError):
        AbibliaDigitalProvider("nvi", client=httpx.Client()).get_chapter(JOAO, 3)


@respx.mock
def test_remote_server_error_is_unavailable() -> None:
    respx.get(URL).mock(return_value=httpx.Response(503))

    with pytest.raises(ProviderUnavailableError):
        AbibliaDigitalProvider("nvi", client=httpx.Client()).get_chapter(JOAO, 3)


@respx.mock
def test_remote_network_error_is_unavailable() -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectError("boom"))

    with pytest.raises(ProviderUnavailableError):
        AbibliaDigitalProvider("nvi", client=httpx.Client()).get_chapter(JOAO, 3)


@respx.mock
@pytest.mark.parametrize(
    "body",
    [{"unexpected": True}, {"verses": [{"number": 1, "text": "a"}, {"number": 3, "text": "c"}]}],
    ids=["malformed", "non-contiguous"],
)
def test_remote_bad_payload_is_unavailable(body: dict[str, object]) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json=body))

    with pytest.raises(ProviderUnavailableError):
        AbibliaDigitalProvider("nvi", client=httpx.Client()).get_chapter(JOAO, 3)


def test_remote_version_is_uppercase() -> None:
    assert AbibliaDigitalProvider("nvi", client=httpx.Client()).version == "NVI"


# --- local provider ----------------------------------------------------------------------


def test_local_bundled_data_is_complete_and_correct() -> None:
    provider = LocalBibleProvider(DATA_FILE, version="ALM1911")
    salmos = get_book("sl")
    assert salmos is not None

    assert len(provider.get_chapter(JOAO, 3)) == 36
    assert "Deus" in provider.get_chapter(JOAO, 3)[15]
    assert provider.get_chapter(salmos, 150)
    with pytest.raises(InvalidReferenceError):
        provider.get_chapter(salmos, 151)


def test_local_missing_file_is_unavailable(tmp_path: Path) -> None:
    with pytest.raises(ProviderUnavailableError):
        LocalBibleProvider(tmp_path / "missing.json", version="X").get_chapter(JOAO, 3)


def test_local_wrong_book_count_is_unavailable(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('[{"chapters": [["a"]]}]', encoding="utf-8")

    with pytest.raises(ProviderUnavailableError):
        LocalBibleProvider(bad, version="X").get_chapter(JOAO, 3)


# --- service -----------------------------------------------------------------------------


def test_service_slices_requested_verses() -> None:
    passage = BibleService([FakeProvider("A")]).fetch(make_ref(start=2, end=4))

    assert [verse.number for verse in passage.verses] == [2, 3, 4]
    assert [verse.text for verse in passage.verses] == ["verse 2", "verse 3", "verse 4"]
    assert passage.version == "A"


def test_service_falls_back_when_primary_unavailable(unavailable: Exception) -> None:
    primary = FakeProvider("PRIMARY", error=unavailable)
    fallback = FakeProvider("FALLBACK")

    passage = BibleService([primary, fallback]).fetch(make_ref())

    assert passage.version == "FALLBACK"
    assert primary.calls == 1


def test_service_does_not_fall_back_on_invalid_reference(invalid: Exception) -> None:
    fallback = FakeProvider("FALLBACK")

    with pytest.raises(InvalidReferenceError):
        BibleService([FakeProvider("PRIMARY", error=invalid), fallback]).fetch(make_ref())

    assert fallback.calls == 0


def test_service_raises_when_all_providers_fail(unavailable: Exception) -> None:
    providers = [FakeProvider("A", error=unavailable), FakeProvider("B", error=unavailable)]

    with pytest.raises(AllProvidersFailedError):
        BibleService(providers).fetch(make_ref())


def test_service_rejects_verse_range_beyond_chapter() -> None:
    with pytest.raises(InvalidReferenceError, match="out of range"):
        BibleService([FakeProvider(verses=["a", "b", "c"])]).fetch(make_ref(start=3, end=5))


def test_service_requires_a_provider() -> None:
    with pytest.raises(ValueError):
        BibleService([])
