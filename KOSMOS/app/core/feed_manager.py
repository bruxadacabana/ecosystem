"""CRUD de feeds, categorias e artigos. Única porta de acesso ao banco na UI."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.database import get_session
from app.core.models import Article, ArticleTag, Category, Feed, Highlight, ReadSession, Tag

log = logging.getLogger("kosmos.feed_manager")


def _detect_lang(text: str) -> str | None:
    """Detecta idioma de um trecho de texto. Retorna código ISO 639-1 ou None."""
    try:
        import langdetect
        snippet = text.strip()[:500]
        if len(snippet) < 20:
            return None
        return langdetect.detect(snippet)
    except Exception:
        return None


class FeedManagerError(Exception):
    """Erro de operação no FeedManager."""


class FeedManager:
    """Gerencia o ciclo de vida de feeds, categorias e artigos.

    Cada método abre e fecha sua própria sessão — seguro para chamar de
    qualquer thread, desde que não se compartilhem objetos SQLAlchemy entre
    threads.
    """

    # ------------------------------------------------------------------
    # Categorias
    # ------------------------------------------------------------------

    def get_categories(self) -> list[Category]:
        session = get_session()
        try:
            cats = (
                session.query(Category)
                .order_by(Category.position, Category.name)
                .all()
            )
            for c in cats:
                session.expunge(c)
            return cats
        finally:
            session.close()

    def add_category(self, name: str) -> Category:
        session = get_session()
        try:
            cat = Category(name=name.strip())
            session.add(cat)
            session.commit()
            session.refresh(cat)   # recarrega id e campos gerados pelo DB
            session.expunge(cat)
            log.info("Categoria criada: %r", cat.name)
            return cat
        except SQLAlchemyError as exc:
            session.rollback()
            raise FeedManagerError(f"Erro ao criar categoria: {exc}") from exc
        finally:
            session.close()

    def rename_category(self, category_id: int, name: str) -> None:
        session = get_session()
        try:
            cat = session.get(Category, category_id)
            if cat is None:
                raise FeedManagerError(f"Categoria {category_id} não encontrada.")
            cat.name = name.strip()
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            raise FeedManagerError(f"Erro ao renomear categoria: {exc}") from exc
        finally:
            session.close()

    def delete_category(self, category_id: int) -> None:
        """Remove a categoria. Os feeds ficam sem categoria (SET NULL)."""
        session = get_session()
        try:
            cat = session.get(Category, category_id)
            if cat is None:
                raise FeedManagerError(f"Categoria {category_id} não encontrada.")
            session.delete(cat)
            session.commit()
            log.info("Categoria removida: id=%d", category_id)
        except SQLAlchemyError as exc:
            session.rollback()
            raise FeedManagerError(f"Erro ao excluir categoria: {exc}") from exc
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Feeds
    # ------------------------------------------------------------------

    def get_feeds(self, category_id: int | None = None) -> list[Feed]:
        session = get_session()
        try:
            q = session.query(Feed)
            if category_id is not None:
                q = q.filter(Feed.category_id == category_id)
            feeds = q.order_by(Feed.position, Feed.name).all()
            for f in feeds:
                session.expunge(f)
            return feeds
        finally:
            session.close()

    def get_active_feeds(self) -> list[Feed]:
        session = get_session()
        try:
            feeds = (
                session.query(Feed)
                .filter(Feed.active == 1)
                .order_by(Feed.position, Feed.name)
                .all()
            )
            for f in feeds:
                session.expunge(f)
            return feeds
        finally:
            session.close()

    def get_feed(self, feed_id: int) -> Feed | None:
        session = get_session()
        try:
            feed = session.get(Feed, feed_id)
            if feed:
                session.expunge(feed)
            return feed
        finally:
            session.close()

    def add_feed(
        self,
        url: str,
        name: str,
        feed_type: str,
        category_id: int | None = None,
    ) -> Feed:
        session = get_session()
        try:
            feed = Feed(
                url=url.strip(),
                name=name.strip(),
                feed_type=feed_type,
                category_id=category_id,
            )
            session.add(feed)
            session.commit()
            session.refresh(feed)
            session.expunge(feed)
            log.info("Feed adicionado: %r (%s)", feed.name, feed.feed_type)
            return feed
        except SQLAlchemyError as exc:
            session.rollback()
            raise FeedManagerError(f"Erro ao adicionar feed: {exc}") from exc
        finally:
            session.close()

    def delete_feed(self, feed_id: int) -> None:
        """Remove o feed e todos os seus artigos (CASCADE)."""
        session = get_session()
        try:
            feed = session.get(Feed, feed_id)
            if feed is None:
                raise FeedManagerError(f"Feed {feed_id} não encontrado.")
            session.delete(feed)
            session.commit()
            log.info("Feed removido: id=%d", feed_id)
        except SQLAlchemyError as exc:
            session.rollback()
            raise FeedManagerError(f"Erro ao excluir feed: {exc}") from exc
        finally:
            session.close()

    def set_feed_active(self, feed_id: int, active: bool) -> None:
        """Pausa ou reativa um feed."""
        session = get_session()
        try:
            feed = session.get(Feed, feed_id)
            if feed is None:
                raise FeedManagerError(f"Feed {feed_id} não encontrado.")
            feed.active = 1 if active else 0
            session.commit()
            log.info("Feed %d: active=%s", feed_id, active)
        except SQLAlchemyError as exc:
            session.rollback()
            raise FeedManagerError(f"Erro ao alterar feed: {exc}") from exc
        finally:
            session.close()

    def update_feed_metadata(
        self,
        feed_id: int,
        etag: str | None = None,
        last_modified: str | None = None,
        last_error: str | None = None,
        clear_error: bool = False,
    ) -> None:
        session = get_session()
        try:
            feed = session.get(Feed, feed_id)
            if feed is None:
                return
            feed.last_fetched = datetime.utcnow()
            if etag is not None:
                feed.etag = etag
            if last_modified is not None:
                feed.last_modified = last_modified
            if last_error is not None:
                feed.last_error = last_error
            if clear_error:
                feed.last_error = None
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao atualizar metadata do feed %d: %s", feed_id, exc)
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Artigos
    # ------------------------------------------------------------------

    def save_articles(self, feed_id: int, articles_data: list[dict[str, Any]]) -> int:
        """Salva artigos novos no banco (ignora duplicatas por guid).

        Returns:
            Número de artigos efetivamente inseridos.
        """
        if not articles_data:
            return 0

        saved = 0
        session = get_session()
        try:
            for data in articles_data:
                lang = _detect_lang(
                    data.get("title", "") + " " + (data.get("summary") or "")
                )
                article = Article(
                    feed_id      = feed_id,
                    guid         = data["guid"],
                    title        = data.get("title", "(sem título)"),
                    url          = data.get("url"),
                    author       = data.get("author"),
                    published_at = data.get("published_at"),
                    summary      = data.get("summary"),
                    content_full = data.get("content"),
                    language     = lang,
                    extra_json   = json.dumps(data["extra"]) if data.get("extra") else None,
                )
                session.add(article)
                try:
                    session.flush()
                    saved += 1
                except IntegrityError:
                    session.rollback()  # duplicate guid — skip
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao salvar artigos do feed %d: %s", feed_id, exc)
        finally:
            session.close()

        if saved:
            log.debug("Feed %d: %d artigo(s) novos salvos.", feed_id, saved)
        return saved

    def get_articles(
        self,
        feed_id: int,
        unread_only: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Article]:
        session = get_session()
        try:
            q = session.query(Article).filter(Article.feed_id == feed_id)
            if unread_only:
                q = q.filter(Article.is_read == 0)
            q = q.order_by(Article.published_at.desc().nullslast(), Article.fetched_at.desc())
            q = q.limit(limit).offset(offset)
            articles = q.all()
            for a in articles:
                session.expunge(a)
            return articles
        finally:
            session.close()

    def get_articles_filtered(
        self,
        feed_ids: list[int] | None = None,
        category_ids: list[int] | None = None,
        search: str | None = None,
        unread_only: bool = False,
        date_from: "datetime | None" = None,
        blocked_keywords: list[str] | None = None,
        hide_duplicates: bool = False,
        language: str | None = None,
        limit: int = 300,
        offset: int = 0,
    ) -> list[Article]:
        """Retorna artigos com filtros combinados."""
        from sqlalchemy import or_
        session = get_session()
        try:
            q = session.query(Article)
            if feed_ids:
                q = q.filter(Article.feed_id.in_(feed_ids))
            elif category_ids:
                q = q.join(Feed).filter(Feed.category_id.in_(category_ids))
            if unread_only:
                q = q.filter(Article.is_read == 0)
            if search and search.strip():
                term = f"%{search.strip()}%"
                q = q.filter(
                    or_(Article.title.ilike(term), Article.summary.ilike(term))
                )
            if date_from is not None:
                q = q.filter(Article.published_at >= date_from)
            if blocked_keywords:
                for kw in blocked_keywords:
                    kw = kw.strip()
                    if kw:
                        term = f"%{kw}%"
                        q = q.filter(~Article.title.ilike(term))
            if hide_duplicates:
                q = q.filter(Article.duplicate_of.is_(None))
            if language:
                q = q.filter(Article.language == language)
            q = q.order_by(Article.published_at.desc().nullslast(), Article.fetched_at.desc())
            q = q.limit(limit).offset(offset)
            articles = q.all()
            for a in articles:
                session.expunge(a)
            return articles
        finally:
            session.close()

    def get_distinct_languages(self) -> list[str]:
        """Retorna lista de códigos de idioma presentes nos artigos, ordenada."""
        session = get_session()
        try:
            rows = (
                session.query(Article.language)
                .filter(Article.language.isnot(None))
                .distinct()
                .order_by(Article.language)
                .all()
            )
            return [r[0] for r in rows]
        finally:
            session.close()

    def deduplicate_recent(self, feed_id: int, hours: int = 48, threshold: float = 85.0) -> int:
        """Marca artigos recém-salvos do feed como duplicatas se um artigo similar
        já existir em outro feed (janela de `hours` horas). Retorna o número de
        duplicatas encontradas.
        """
        try:
            from rapidfuzz import fuzz
        except ImportError:
            return 0

        session = get_session()
        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)

            # Artigos novos deste feed ainda não marcados
            new_articles = (
                session.query(Article)
                .filter(
                    Article.feed_id == feed_id,
                    Article.fetched_at >= cutoff,
                    Article.duplicate_of.is_(None),
                    Article.is_saved == 0,
                )
                .all()
            )
            if not new_articles:
                return 0

            # Artigos recentes de outros feeds (candidatos de referência)
            existing = (
                session.query(Article)
                .filter(
                    Article.feed_id != feed_id,
                    Article.fetched_at >= cutoff,
                    Article.duplicate_of.is_(None),
                )
                .all()
            )
            if not existing:
                return 0

            duplicates_found = 0
            for article in new_articles:
                for candidate in existing:
                    score = fuzz.token_sort_ratio(article.title, candidate.title)
                    if score >= threshold:
                        article.duplicate_of = candidate.id
                        duplicates_found += 1
                        break

            if duplicates_found:
                session.commit()
                log.info("Feed %d: %d duplicata(s) marcada(s).", feed_id, duplicates_found)
            return duplicates_found
        except Exception as exc:
            session.rollback()
            log.error("Erro na deduplicação do feed %d: %s", feed_id, exc)
            return 0
        finally:
            session.close()

    def get_all_unread(self, limit: int = 500) -> list[Article]:
        session = get_session()
        try:
            articles = (
                session.query(Article)
                .filter(Article.is_read == 0)
                .order_by(Article.published_at.desc().nullslast())
                .limit(limit)
                .all()
            )
            for a in articles:
                session.expunge(a)
            return articles
        finally:
            session.close()

    def get_saved_articles(self, limit: int = 200) -> list[Article]:
        session = get_session()
        try:
            articles = (
                session.query(Article)
                .filter(Article.is_saved == 1)
                .order_by(Article.saved_at.desc())
                .limit(limit)
                .all()
            )
            for a in articles:
                session.expunge(a)
            return articles
        finally:
            session.close()

    def get_unread_count(self, feed_id: int | None = None) -> int:
        session = get_session()
        try:
            q = session.query(func.count(Article.id)).filter(Article.is_read == 0)
            if feed_id is not None:
                q = q.filter(Article.feed_id == feed_id)
            return q.scalar() or 0
        finally:
            session.close()

    def mark_as_read(self, article_id: int) -> None:
        session = get_session()
        try:
            article = session.get(Article, article_id)
            if article and not article.is_read:
                article.is_read = 1
                article.read_at = datetime.utcnow()
                session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao marcar artigo %d como lido: %s", article_id, exc)
        finally:
            session.close()

    def mark_as_unread(self, article_id: int) -> None:
        session = get_session()
        try:
            article = session.get(Article, article_id)
            if article and article.is_read:
                article.is_read = 0
                article.read_at = None
                session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao marcar artigo %d como não lido: %s", article_id, exc)
        finally:
            session.close()

    def mark_feed_as_read(self, feed_id: int) -> None:
        session = get_session()
        try:
            now = datetime.utcnow()
            (
                session.query(Article)
                .filter(Article.feed_id == feed_id, Article.is_read == 0)
                .update({"is_read": 1, "read_at": now})
            )
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao marcar feed %d como lido: %s", feed_id, exc)
        finally:
            session.close()

    def mark_articles_as_read(self, article_ids: list[int]) -> None:
        """Marca uma lista de artigos como lidos."""
        if not article_ids:
            return
        session = get_session()
        try:
            now = datetime.utcnow()
            session.query(Article).filter(
                Article.id.in_(article_ids), Article.is_read == 0
            ).update({"is_read": 1, "read_at": now}, synchronize_session=False)
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao marcar artigos como lidos: %s", exc)
        finally:
            session.close()

    def get_article(self, article_id: int) -> Article | None:
        """Retorna um artigo pelo id (ou None se não existir)."""
        session = get_session()
        try:
            article = session.get(Article, article_id)
            if article:
                session.expunge(article)
            return article
        finally:
            session.close()

    def toggle_saved(self, article_id: int) -> bool:
        """Alterna o estado salvo de um artigo. Retorna o novo estado."""
        session = get_session()
        try:
            article = session.get(Article, article_id)
            if article is None:
                raise FeedManagerError(f"Artigo {article_id} não encontrado.")
            new_state = 0 if article.is_saved else 1
            article.is_saved = new_state
            article.saved_at = datetime.utcnow() if new_state else None
            session.commit()
            return bool(new_state)
        except SQLAlchemyError as exc:
            session.rollback()
            raise FeedManagerError(f"Erro ao alterar estado salvo: {exc}") from exc
        finally:
            session.close()

    def toggle_read(self, article_id: int) -> bool:
        """Alterna lido/não lido de um artigo. Retorna o novo estado."""
        session = get_session()
        try:
            article = session.get(Article, article_id)
            if article is None:
                return False
            new_state = 0 if article.is_read else 1
            article.is_read = new_state
            article.read_at = datetime.utcnow() if new_state else None
            session.commit()
            return bool(new_state)
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao alternar lido para artigo %d: %s", article_id, exc)
            return False
        finally:
            session.close()

    def save_article_scroll(self, article_id: int, scroll_pos: int) -> None:
        """Persiste a posição de scroll de um artigo."""
        if scroll_pos <= 0:
            return
        session = get_session()
        try:
            article = session.get(Article, article_id)
            if article:
                article.scroll_pos = scroll_pos
                session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao salvar scroll do artigo %d: %s", article_id, exc)
        finally:
            session.close()

    def save_ai_summary(self, article_id: int, summary: str) -> None:
        """Persiste o resumo gerado por IA no artigo."""
        session = get_session()
        try:
            article = session.get(Article, article_id)
            if article:
                article.ai_summary = summary
                session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao salvar resumo IA do artigo %d: %s", article_id, exc)
        finally:
            session.close()

    def get_unanalyzed_article_ids(self, limit: int = 50) -> list[int]:
        """Retorna IDs de artigos sem análise de IA (ai_sentiment IS NULL)."""
        session = get_session()
        try:
            rows = (
                session.query(Article.id)
                .filter(Article.ai_sentiment.is_(None))
                .order_by(Article.published_at.desc().nullslast(), Article.fetched_at.desc())
                .limit(limit)
                .all()
            )
            return [r.id for r in rows]
        finally:
            session.close()

    def save_ai_tags_json(self, article_id: int, tags: list[str]) -> None:
        """Persiste tags geradas por IA no campo ai_tags (JSON) do artigo."""
        import json as _j
        session = get_session()
        try:
            article = session.get(Article, article_id)
            if article:
                article.ai_tags = _j.dumps(tags, ensure_ascii=False)
                session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao salvar ai_tags do artigo %d: %s", article_id, exc)
        finally:
            session.close()

    def save_ai_analysis(
        self,
        article_id: int,
        sentiment:  float | None = None,
        clickbait:  float | None = None,
        five_ws:    str   | None = None,
        entities:   str   | None = None,
    ) -> None:
        """Persiste resultados do _AnalyzeWorker (sentimento, clickbait, 5Ws, entidades)."""
        session = get_session()
        try:
            article = session.get(Article, article_id)
            if article:
                if sentiment is not None:
                    article.ai_sentiment = sentiment
                if clickbait is not None:
                    article.ai_clickbait = clickbait
                if five_ws is not None:
                    article.ai_5ws = five_ws
                if entities is not None:
                    article.ai_entities = entities
                session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao salvar análise IA do artigo %d: %s", article_id, exc)
        finally:
            session.close()

    def save_ai_5ws(self, article_id: int, json_str: str) -> None:
        """Persiste a análise 5Ws gerada por IA no artigo."""
        session = get_session()
        try:
            article = session.get(Article, article_id)
            if article:
                article.ai_5ws = json_str
                session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao salvar 5Ws do artigo %d: %s", article_id, exc)
        finally:
            session.close()

    def save_embedding(self, article_id: int, blob: bytes) -> None:
        """Persiste o embedding vetorial do artigo (BLOB de float32)."""
        session = get_session()
        try:
            article = session.get(Article, article_id)
            if article:
                article.embedding = blob
                session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao salvar embedding do artigo %d: %s", article_id, exc)
        finally:
            session.close()

    def get_user_profile_embedding(self) -> list[float] | None:
        """Média dos embeddings dos artigos lidos ou salvos.

        Retorna None se nenhum artigo com embedding existir ainda.
        """
        session = get_session()
        try:
            rows = (
                session.query(Article.embedding)
                .filter(
                    ((Article.is_read == 1) | (Article.is_saved == 1)),
                    Article.embedding.isnot(None),
                )
                .all()
            )
            if not rows:
                return None
            from app.core.ai_bridge import AiBridge
            vecs = [AiBridge.blob_to_vec(r.embedding) for r in rows if r.embedding]
            if not vecs:
                return None
            return AiBridge.average_vecs(vecs)
        except Exception as exc:
            log.error("Erro ao calcular perfil de embeddings: %s", exc)
            return None
        finally:
            session.close()

    def update_all_relevance_scores(self, profile: list[float]) -> None:
        """Atualiza ai_relevance de todos os artigos que possuem embedding."""
        session = get_session()
        try:
            from app.core.ai_bridge import AiBridge
            rows = (
                session.query(Article)
                .filter(Article.embedding.isnot(None))
                .all()
            )
            for article in rows:
                if article.embedding:
                    vec = AiBridge.blob_to_vec(article.embedding)
                    article.ai_relevance = AiBridge.cosine_similarity(vec, profile)
            session.commit()
        except Exception as exc:
            session.rollback()
            log.error("Erro ao atualizar scores de relevância: %s", exc)
        finally:
            session.close()

    def update_article_content(
        self,
        article_id: int,
        content_html: str,
        scrape_status: str,
    ) -> None:
        """Persiste o conteúdo scraped e o status no artigo."""
        session = get_session()
        try:
            article = session.get(Article, article_id)
            if article:
                article.content_full  = content_html
                article.scrape_status = scrape_status
                session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error(
                "Erro ao atualizar conteúdo do artigo %d: %s", article_id, exc
            )
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Estatísticas de dashboard
    # ------------------------------------------------------------------

    def get_stats_summary(self) -> dict:
        """Retorna contadores globais para o dashboard."""
        session = get_session()
        try:
            total_read  = session.query(func.count(Article.id)).filter(Article.is_read == 1).scalar() or 0
            total_saved = session.query(func.count(Article.id)).filter(Article.is_saved == 1).scalar() or 0
            total_feeds = session.query(func.count(Feed.id)).filter(Feed.active == 1).scalar() or 0
            return {"total_read": total_read, "total_saved": total_saved, "active_feeds": total_feeds}
        finally:
            session.close()

    def get_top_feeds_by_reads(self, limit: int = 5) -> list[tuple[Feed, int]]:
        """Retorna os feeds com mais artigos lidos, em ordem decrescente."""
        session = get_session()
        try:
            rows = (
                session.query(Feed, func.count(Article.id).label("cnt"))
                .join(Article, Article.feed_id == Feed.id)
                .filter(Article.is_read == 1)
                .group_by(Feed.id)
                .order_by(func.count(Article.id).desc())
                .limit(limit)
                .all()
            )
            result = []
            for feed, cnt in rows:
                session.expunge(feed)
                result.append((feed, int(cnt)))
            return result
        finally:
            session.close()

    def get_top_tags(self, limit: int = 5) -> list[tuple[Tag, int]]:
        """Retorna as tags mais usadas em artigos, em ordem decrescente."""
        session = get_session()
        try:
            rows = (
                session.query(Tag, func.count(ArticleTag.article_id).label("cnt"))
                .join(ArticleTag, ArticleTag.tag_id == Tag.id)
                .group_by(Tag.id)
                .order_by(func.count(ArticleTag.article_id).desc())
                .limit(limit)
                .all()
            )
            result = []
            for tag, cnt in rows:
                session.expunge(tag)
                result.append((tag, int(cnt)))
            return result
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def get_tags(self) -> list[Tag]:
        """Retorna todas as tags existentes ordenadas por nome."""
        session = get_session()
        try:
            tags = session.query(Tag).order_by(Tag.name).all()
            for t in tags:
                session.expunge(t)
            return tags
        finally:
            session.close()

    def create_tag(self, name: str, color: str = "#8B7355") -> Tag:
        """Cria uma nova tag global. Lança FeedManagerError se o nome já existe."""
        session = get_session()
        try:
            tag = Tag(name=name.strip(), color=color)
            session.add(tag)
            session.commit()
            session.refresh(tag)
            session.expunge(tag)
            log.info("Tag criada: %r", tag.name)
            return tag
        except IntegrityError:
            session.rollback()
            raise FeedManagerError(f"Tag {name!r} já existe.")
        except SQLAlchemyError as exc:
            session.rollback()
            raise FeedManagerError(f"Erro ao criar tag: {exc}") from exc
        finally:
            session.close()

    def delete_tag(self, tag_id: int) -> None:
        """Remove a tag e todas as suas associações com artigos."""
        session = get_session()
        try:
            tag = session.get(Tag, tag_id)
            if tag is None:
                raise FeedManagerError(f"Tag {tag_id} não encontrada.")
            session.delete(tag)
            session.commit()
            log.info("Tag removida: id=%d", tag_id)
        except SQLAlchemyError as exc:
            session.rollback()
            raise FeedManagerError(f"Erro ao excluir tag: {exc}") from exc
        finally:
            session.close()

    def get_article_tags(self, article_id: int) -> list[Tag]:
        """Retorna as tags associadas a um artigo."""
        session = get_session()
        try:
            article = session.get(Article, article_id)
            if article is None:
                return []
            tags = list(article.tags)
            for t in tags:
                session.expunge(t)
            return tags
        finally:
            session.close()

    def add_tag_to_article(self, article_id: int, tag_id: int) -> None:
        """Associa uma tag a um artigo (idempotente)."""
        session = get_session()
        try:
            exists = session.get(ArticleTag, (article_id, tag_id))
            if exists is None:
                session.add(ArticleTag(article_id=article_id, tag_id=tag_id))
                session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao adicionar tag %d ao artigo %d: %s", tag_id, article_id, exc)
        finally:
            session.close()

    def remove_tag_from_article(self, article_id: int, tag_id: int) -> None:
        """Remove a associação entre uma tag e um artigo."""
        session = get_session()
        try:
            assoc = session.get(ArticleTag, (article_id, tag_id))
            if assoc:
                session.delete(assoc)
                session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao remover tag %d ao artigo %d: %s", tag_id, article_id, exc)
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Highlights / Anotações
    # ------------------------------------------------------------------

    def get_highlights(self, article_id: int) -> list[Highlight]:
        """Retorna os destaques de um artigo ordenados por data de criação."""
        session = get_session()
        try:
            hls = (
                session.query(Highlight)
                .filter(Highlight.article_id == article_id)
                .order_by(Highlight.created_at)
                .all()
            )
            for h in hls:
                session.expunge(h)
            return hls
        finally:
            session.close()

    def add_highlight(
        self,
        article_id: int,
        text: str,
        note: str | None = None,
        color: str = "#E6B43C",
    ) -> Highlight:
        """Salva um novo destaque. Retorna o objeto persistido."""
        session = get_session()
        try:
            hl = Highlight(article_id=article_id, text=text, note=note, color=color)
            session.add(hl)
            session.commit()
            session.refresh(hl)
            session.expunge(hl)
            log.debug("Destaque adicionado: article=%d text=%r", article_id, text[:30])
            return hl
        except SQLAlchemyError as exc:
            session.rollback()
            raise FeedManagerError(f"Erro ao salvar destaque: {exc}") from exc
        finally:
            session.close()

    def update_highlight_note(self, highlight_id: int, note: str | None) -> None:
        """Atualiza a anotação de um destaque."""
        session = get_session()
        try:
            hl = session.get(Highlight, highlight_id)
            if hl:
                hl.note = note
                session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao atualizar nota do destaque %d: %s", highlight_id, exc)
        finally:
            session.close()

    def delete_highlight(self, highlight_id: int) -> None:
        """Remove um destaque pelo id."""
        session = get_session()
        try:
            hl = session.get(Highlight, highlight_id)
            if hl:
                session.delete(hl)
                session.commit()
                log.debug("Destaque removido: id=%d", highlight_id)
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao remover destaque %d: %s", highlight_id, exc)
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Sessões de leitura
    # ------------------------------------------------------------------

    def start_read_session(self, article_id: int, feed_id: int) -> int:
        """Registra o início de uma sessão de leitura. Retorna o id da sessão (-1 em erro)."""
        session = get_session()
        try:
            rs = ReadSession(article_id=article_id, feed_id=feed_id)
            session.add(rs)
            session.commit()
            return rs.id
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao iniciar sessão de leitura: %s", exc)
            return -1
        finally:
            session.close()

    def end_read_session(self, session_id: int, duration_sec: int) -> None:
        """Finaliza uma sessão de leitura registrando a duração."""
        if session_id < 0:
            return
        session = get_session()
        try:
            rs = session.get(ReadSession, session_id)
            if rs:
                rs.duration_sec = duration_sec
                session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro ao finalizar sessão de leitura %d: %s", session_id, exc)
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Purgação
    # ------------------------------------------------------------------

    def purge_old_articles(self, read_days: int = 30, unread_days: int = 90) -> int:
        """Remove artigos antigos não salvos. Retorna o número removido."""
        session = get_session()
        try:
            now = datetime.utcnow()
            cutoff_read   = now - timedelta(days=read_days)
            cutoff_unread = now - timedelta(days=unread_days)

            # Artigos lidos mais antigos que cutoff_read
            deleted_read = (
                session.query(Article)
                .filter(
                    Article.is_saved == 0,
                    Article.is_read  == 1,
                    Article.fetched_at < cutoff_read,
                )
                .delete(synchronize_session=False)
            )

            # Artigos não lidos mais antigos que cutoff_unread
            deleted_unread = (
                session.query(Article)
                .filter(
                    Article.is_saved == 0,
                    Article.is_read  == 0,
                    Article.fetched_at < cutoff_unread,
                )
                .delete(synchronize_session=False)
            )

            session.commit()
            total = (deleted_read or 0) + (deleted_unread or 0)
            if total:
                log.info("Purgação: %d artigo(s) removidos.", total)
            return total
        except SQLAlchemyError as exc:
            session.rollback()
            log.error("Erro durante purgação: %s", exc)
            return 0
        finally:
            session.close()
