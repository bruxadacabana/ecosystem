"""Modelos SQLAlchemy do KOSMOS."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.base import Base


class Category(Base):
    """Pasta de feeds criada pelo usuário."""

    __tablename__ = "categories"

    id:         int      = Column(Integer, primary_key=True, autoincrement=True)
    name:       str      = Column(String, nullable=False)
    position:   int      = Column(Integer, default=0)
    created_at: datetime = Column(DateTime, default=datetime.utcnow)

    feeds = relationship("Feed", back_populates="category", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r}>"


class Feed(Base):
    """Fonte de conteúdo: RSS, Reddit, YouTube, Tumblr, Substack, Mastodon."""

    __tablename__ = "feeds"

    id:            int            = Column(Integer, primary_key=True, autoincrement=True)
    category_id:   int | None     = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    name:          str            = Column(String, nullable=False)
    url:           str            = Column(String, nullable=False)
    feed_type:     str            = Column(String, nullable=False)  # rss|reddit|youtube|tumblr|substack|mastodon
    favicon_path:  str | None     = Column(String, nullable=True)
    etag:          str | None     = Column(String, nullable=True)
    last_modified: str | None     = Column(String, nullable=True)
    last_fetched:  datetime | None = Column(DateTime, nullable=True)
    last_error:    str | None     = Column(Text, nullable=True)
    position:      int            = Column(Integer, default=0)
    active:        int            = Column(Integer, default=1)   # 0 = pausado
    created_at:    datetime       = Column(DateTime, default=datetime.utcnow)

    category = relationship("Category", back_populates="feeds")
    articles = relationship(
        "Article",
        back_populates="feed",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return f"<Feed id={self.id} name={self.name!r} type={self.feed_type!r}>"


class Article(Base):
    """Item de conteúdo de um feed."""

    __tablename__ = "articles"

    id:            int            = Column(Integer, primary_key=True, autoincrement=True)
    feed_id:       int            = Column(Integer, ForeignKey("feeds.id", ondelete="CASCADE"), nullable=False)
    guid:          str            = Column(String, nullable=False)
    title:         str            = Column(String, nullable=False)
    url:           str | None     = Column(String, nullable=True)
    author:        str | None     = Column(String, nullable=True)
    published_at:  datetime | None = Column(DateTime, nullable=True)
    fetched_at:    datetime       = Column(DateTime, default=datetime.utcnow)
    summary:       str | None     = Column(Text, nullable=True)    # conteúdo do RSS (pode ser truncado)
    content_full:  str | None     = Column(Text, nullable=True)    # conteúdo scraped (completo)
    content_type:  str            = Column(String, default="html")
    scrape_status: str            = Column(String, default="none")    # none|full|partial|failed
    integrity:     str            = Column(String, default="unknown") # full|truncated|unknown
    is_read:       int            = Column(Integer, default=0)
    is_saved:      int            = Column(Integer, default=0)
    read_at:       datetime | None = Column(DateTime, nullable=True)
    saved_at:      datetime | None = Column(DateTime, nullable=True)
    scroll_pos:    int            = Column(Integer, default=0)    # posição de scroll salva
    duplicate_of:  int | None     = Column(Integer, ForeignKey("articles.id", ondelete="SET NULL"), nullable=True)
    language:      str | None     = Column(String, nullable=True)  # código ISO 639-1 detectado
    extra_json:    str | None     = Column(Text, nullable=True)   # JSON extra por plataforma
    # FASE F — IA local
    ai_summary:    str | None     = Column(Text, nullable=True)   # resumo gerado por LLM
    ai_tags:       str | None     = Column(Text, nullable=True)   # JSON: lista de tags sugeridas
    embedding:     bytes | None   = Column(LargeBinary, nullable=True)  # vetor float32 serializado
    ai_relevance:  float | None   = Column(Float, nullable=True)  # cosine similarity com perfil
    ai_5ws:        str | None     = Column(Text, nullable=True)   # JSON: {who,what,when,where,why}
    ai_sentiment:  float | None   = Column(Float, nullable=True)  # -1.0 negativo ↔ +1.0 positivo
    ai_clickbait:  float | None   = Column(Float, nullable=True)  # 0.0 sem clickbait ↔ 1.0 puro
    ai_entities:   str | None     = Column(Text, nullable=True)   # JSON: {people,orgs,places}

    feed          = relationship("Feed", back_populates="articles")
    tags          = relationship("Tag", secondary="article_tags", back_populates="articles")
    read_sessions = relationship("ReadSession", back_populates="article")

    __table_args__ = (UniqueConstraint("feed_id", "guid"),)

    def __repr__(self) -> str:
        return f"<Article id={self.id} title={self.title!r:.40}>"


class Tag(Base):
    """Tag manual global — pode ser associada a qualquer artigo salvo."""

    __tablename__ = "tags"

    id:    int = Column(Integer, primary_key=True, autoincrement=True)
    name:  str = Column(String, nullable=False, unique=True)
    color: str = Column(String, default="#8B7355")

    articles = relationship("Article", secondary="article_tags", back_populates="tags")

    def __repr__(self) -> str:
        return f"<Tag id={self.id} name={self.name!r}>"


class ArticleTag(Base):
    """Tabela de associação many-to-many entre Article e Tag."""

    __tablename__ = "article_tags"

    article_id: int = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    tag_id:     int = Column(Integer, ForeignKey("tags.id",     ondelete="CASCADE"), primary_key=True)


class Highlight(Base):
    """Destaque de texto em um artigo, com anotação opcional."""

    __tablename__ = "highlights"

    id:         int           = Column(Integer, primary_key=True, autoincrement=True)
    article_id: int           = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    text:       str           = Column(Text, nullable=False)
    note:       str | None    = Column(Text, nullable=True)
    color:      str           = Column(String, default="#E6B43C")
    created_at: datetime      = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Highlight id={self.id} article_id={self.article_id} text={self.text!r:.30}>"


class ReadSession(Base):
    """Sessão de leitura — registra tempo por artigo para estatísticas."""

    __tablename__ = "read_sessions"

    id:           int            = Column(Integer, primary_key=True, autoincrement=True)
    article_id:   int | None     = Column(Integer, ForeignKey("articles.id", ondelete="SET NULL"), nullable=True)
    feed_id:      int | None     = Column(Integer, ForeignKey("feeds.id",    ondelete="SET NULL"), nullable=True)
    started_at:   datetime       = Column(DateTime, default=datetime.utcnow)
    duration_sec: int | None     = Column(Integer, nullable=True)

    article = relationship("Article", back_populates="read_sessions")

    def __repr__(self) -> str:
        return f"<ReadSession id={self.id} article_id={self.article_id} duration={self.duration_sec}s>"
