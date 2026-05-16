"""
AKASHA — Perfil persistente de preferências de busca.

Armazena preferências opt-in da usuária e as aplica na camada de pré-retrieval
(antes de executar as buscas), tornando o efeito visível via badge na UI.

Chaves do perfil (tabela search_profile):
  preferred_sources  — JSON list: ["eco", "web", "sites", "papers"]
  boosted_domains    — JSON list de domínios a priorizar (além dos favoritos)

Sinal de re-busca: mesma query em < 5 min indica insatisfação com os resultados
anteriores. Rastreado via search_history — sem armazenamento extra necessário.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

DEFAULT_SOURCES: list[str] = ["eco", "web", "sites"]


@dataclass
class SearchProfile:
    preferred_sources: list[str] = field(default_factory=lambda: [])
    boosted_domains:   list[str] = field(default_factory=list)

    @property
    def has_preferences(self) -> bool:
        return bool(self.preferred_sources or self.boosted_domains)

    @property
    def source_label(self) -> str:
        """Label legível para o badge da UI."""
        labels = {
            "eco":    "arquivo local",
            "web":    "web",
            "sites":  "biblioteca",
            "papers": "artigos",
        }
        if not self.preferred_sources:
            return ""
        return " + ".join(labels.get(s, s) for s in self.preferred_sources)


async def load_profile() -> SearchProfile:
    """Carrega o perfil do banco de dados."""
    from database import get_profile_value
    raw_sources = await get_profile_value("preferred_sources", "")
    raw_domains = await get_profile_value("boosted_domains", "[]")
    try:
        sources = json.loads(raw_sources) if raw_sources else []
    except json.JSONDecodeError:
        sources = []
    try:
        domains = json.loads(raw_domains)
    except json.JSONDecodeError:
        domains = []
    return SearchProfile(preferred_sources=sources, boosted_domains=domains)


async def save_preferred_sources(sources: list[str]) -> None:
    """Salva fontes preferidas no perfil."""
    from database import set_profile_value
    await set_profile_value("preferred_sources", json.dumps(sources))


async def save_boosted_domains(domains: list[str]) -> None:
    """Salva domínios priorizados no perfil."""
    from database import set_profile_value
    await set_profile_value("boosted_domains", json.dumps(domains))


def apply_to_sources(
    profile: SearchProfile,
    src_web: str, src_eco: str, src_sites: str, src_papers: str,
    user_explicit: bool,
) -> tuple[str, str, str, str, bool]:
    """Aplica as preferências do perfil às flags de fonte.

    Só modifica quando o usuário não escolheu explicitamente as fontes
    (user_explicit=False, i.e. veio dos defaults). Retorna (src_web, src_eco,
    src_sites, src_papers, profile_applied).
    """
    if user_explicit or not profile.preferred_sources:
        return src_web, src_eco, src_sites, src_papers, False

    has = profile.preferred_sources
    return (
        "on" if "web"    in has else "",
        "on" if "eco"    in has else "",
        "on" if "sites"  in has else "",
        "on" if "papers" in has else "",
        True,
    )
