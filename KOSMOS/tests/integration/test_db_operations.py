"""
Testes de integração para app/core/database.py (KOSMOS v3).

Verifica fluxos completos: init_db → feeds → artigos → entidades → highlights
→ investigações → FTS → cascade deletes → heartbeat reset.
Usa banco em tmp_path — nunca o DB de produção.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


def _init_and_connect(tmp_path: Path) -> tuple[Path, sqlite3.Connection]:
    import app.core.database as db_module

    db_file = tmp_path / "kosmos_integ.db"
    with patch.object(db_module, "DB_PATH", db_file):
        db_module.init_db()

    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return db_file, conn


class TestDbIntegration:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.db_file, self.conn = _init_and_connect(tmp_path)
        yield
        self.conn.close()

    # ── helpers ────────────────────────────────────────────────────────────

    def _add_feed(self, url: str = "http://tech.com/rss",
                  title: str = "Tech Feed",
                  category: str = "Tecnologia") -> int:
        self.conn.execute(
            "INSERT INTO feeds (url, title, category) VALUES (?, ?, ?)",
            (url, title, category),
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def _add_article(self, feed_id: int, url: str,
                     title: str = "Artigo", content: str = "") -> int:
        self.conn.execute(
            "INSERT INTO articles (feed_id, url, title, content_text) VALUES (?, ?, ?, ?)",
            (feed_id, url, title, content),
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # ── fluxo completo ─────────────────────────────────────────────────────

    def test_full_flow_feed_article_fts(self):
        """Fluxo: criar feed → inserir artigo → buscar via FTS5."""
        fid = self._add_feed()
        aid = self._add_article(
            fid, "http://tech.com/1",
            "Machine Learning na Medicina",
            "Algoritmos detectam doenças precocemente.",
        )

        art = dict(self.conn.execute(
            "SELECT * FROM articles WHERE id=?", (aid,)
        ).fetchone())
        assert art["title"] == "Machine Learning na Medicina"
        assert art["feed_id"] == fid
        assert art["analysis_status"] == "pending"

        rows = self.conn.execute(
            "SELECT rowid FROM fts_articles WHERE fts_articles MATCH 'algoritmos'"
        ).fetchall()
        assert len(rows) >= 1

    def test_article_with_ai_analysis(self):
        """Fluxo: inserir artigo → atualizar com campos AI → verificar JSON."""
        fid = self._add_feed()
        aid = self._add_article(fid, "http://tech.com/2", "IA e Política")

        tags = json.dumps(["inteligência-artificial", "política", "regulação"])
        five_ws = json.dumps({
            "quem": "União Europeia",
            "o_que": "aprova regulação de IA",
            "quando": "2025",
            "onde": "Bruxelas",
            "por_que": "segurança e transparência",
        })
        self.conn.execute(
            """UPDATE articles
               SET ai_tags=?, ai_sentiment='neutro', ai_clickbait_score=0.1,
                   ai_five_ws=?, analysis_status='done', analysis_schema_version=1
             WHERE id=?""",
            (tags, five_ws, aid),
        )
        self.conn.commit()

        row = dict(self.conn.execute("SELECT * FROM articles WHERE id=?", (aid,)).fetchone())
        assert json.loads(row["ai_tags"]) == ["inteligência-artificial", "política", "regulação"]
        assert json.loads(row["ai_five_ws"])["quem"] == "União Europeia"
        assert row["analysis_status"] == "done"
        assert row["ai_sentiment"] == "neutro"

    def test_entity_tracking_flow(self):
        """Fluxo: criar entidade → artigo → vincular → verificar relação."""
        fid = self._add_feed()
        aid = self._add_article(fid, "http://tech.com/3", "Artigo sobre Lula")

        self.conn.execute(
            "INSERT INTO entities (name, entity_type) VALUES ('Lula', 'person')"
        )
        self.conn.commit()
        eid = self.conn.execute(
            "SELECT id FROM entities WHERE name='Lula'"
        ).fetchone()[0]

        self.conn.execute(
            "INSERT INTO article_entities (article_id, entity_id, confidence) VALUES (?, ?, 0.95)",
            (aid, eid),
        )
        self.conn.commit()

        # Verificar que a entidade aparece no artigo
        link = self.conn.execute(
            "SELECT confidence FROM article_entities WHERE article_id=? AND entity_id=?",
            (aid, eid),
        ).fetchone()
        assert link is not None
        assert link[0] == pytest.approx(0.95)

    def test_highlights_flow(self):
        """Fluxo: artigo → destacar trechos com tipos diferentes → recuperar."""
        fid = self._add_feed()
        aid = self._add_article(fid, "http://tech.com/4", "Artigo Marcável")

        self.conn.execute(
            "INSERT INTO highlights (article_id, text, highlight_type, note) "
            "VALUES (?, 'Dado crucial do artigo', 'fact', 'verificar com outra fonte')",
            (aid,),
        )
        self.conn.execute(
            "INSERT INTO highlights (article_id, text, highlight_type) "
            "VALUES (?, 'Isso contradiz a Fonte B', 'contradiction')",
            (aid,),
        )
        self.conn.commit()

        hl = self.conn.execute(
            "SELECT highlight_type, note FROM highlights WHERE article_id=? ORDER BY id",
            (aid,),
        ).fetchall()
        assert len(hl) == 2
        assert hl[0]["highlight_type"] == "fact"
        assert hl[0]["note"] == "verificar com outra fonte"
        assert hl[1]["highlight_type"] == "contradiction"

    def test_investigation_flow(self):
        """Fluxo: criar investigação → adicionar artigos → exportar dados da pasta."""
        fid = self._add_feed()
        aid1 = self._add_article(fid, "http://tech.com/5", "Artigo A")
        aid2 = self._add_article(fid, "http://tech.com/6", "Artigo B")

        self.conn.execute(
            "INSERT INTO investigations (name, description) VALUES (?, ?)",
            ("Op. Vazamento", "Investigação sobre vazamento de dados"),
        )
        self.conn.commit()
        iid = self.conn.execute("SELECT id FROM investigations").fetchone()[0]

        for aid in (aid1, aid2):
            self.conn.execute(
                "INSERT INTO investigation_articles (investigation_id, article_id) VALUES (?, ?)",
                (iid, aid),
            )
        self.conn.commit()

        # Recuperar todos os artigos da investigação
        arts = self.conn.execute(
            """SELECT a.title FROM investigation_articles ia
               JOIN articles a ON a.id = ia.article_id
              WHERE ia.investigation_id = ?
              ORDER BY a.title""",
            (iid,),
        ).fetchall()
        assert len(arts) == 2
        assert arts[0]["title"] == "Artigo A"

    def test_cascade_feed_delete_removes_all(self):
        """Deletar feed deve remover artigos, highlights e investigation_articles."""
        fid = self._add_feed()
        aid = self._add_article(fid, "http://tech.com/7", "Artigo Cascata")
        self.conn.execute(
            "INSERT INTO highlights (article_id, text) VALUES (?, 'trecho')", (aid,)
        )
        self.conn.execute("INSERT INTO investigations (name) VALUES ('Inv')")
        self.conn.commit()
        iid = self.conn.execute("SELECT id FROM investigations").fetchone()[0]
        self.conn.execute(
            "INSERT INTO investigation_articles (investigation_id, article_id) VALUES (?, ?)",
            (iid, aid),
        )
        self.conn.commit()

        self.conn.execute("DELETE FROM feeds WHERE id=?", (fid,))
        self.conn.commit()

        assert self.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 0
        assert self.conn.execute("SELECT COUNT(*) FROM highlights").fetchone()[0] == 0
        assert self.conn.execute("SELECT COUNT(*) FROM investigation_articles").fetchone()[0] == 0
        # A investigação em si permanece (sem artigos)
        assert self.conn.execute("SELECT COUNT(*) FROM investigations").fetchone()[0] == 1

    def test_heartbeat_reset_on_init(self, tmp_path):
        """Artigos travados em 'running' são resetados durante init_db()."""
        import app.core.database as db_module

        db_file = tmp_path / "heartbeat.db"
        with patch.object(db_module, "DB_PATH", db_file):
            db_module.init_db()

        conn = sqlite3.connect(str(db_file))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO feeds (url) VALUES ('http://hb.com/rss')"
        )
        conn.commit()
        conn.execute(
            "INSERT INTO articles (feed_id, url, title, analysis_status, analysis_started_at) "
            "VALUES (1, 'http://hb.com/1', 'Stale', 'running', "
            "strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-10 minutes'))"
        )
        conn.commit()
        conn.close()

        # Chamar init_db() novamente simula reinicialização
        with patch.object(db_module, "DB_PATH", db_file):
            db_module.init_db()

        conn2 = sqlite3.connect(str(db_file))
        row = conn2.execute(
            "SELECT analysis_status FROM articles WHERE url='http://hb.com/1'"
        ).fetchone()
        conn2.close()
        assert row[0] == "pending"

    def test_fts_multi_field_search(self):
        """Busca FTS5 deve encontrar artigos por qualquer campo indexado."""
        fid = self._add_feed()
        self._add_article(
            fid, "http://tech.com/8", "Título Normal",
            content="conteúdo sobre criptomoedas e blockchain"
        )
        # Inserir tags AI depois
        aid = self.conn.execute(
            "SELECT id FROM articles WHERE url='http://tech.com/8'"
        ).fetchone()[0]
        self.conn.execute(
            "UPDATE articles SET ai_tags=? WHERE id=?",
            (json.dumps(["fintech", "descentralização"]), aid),
        )
        self.conn.commit()

        # Busca por conteúdo
        r1 = self.conn.execute(
            "SELECT rowid FROM fts_articles WHERE fts_articles MATCH 'blockchain'"
        ).fetchall()
        # Busca por tag (requer re-trigger — UPDATE atualiza FTS)
        r2 = self.conn.execute(
            "SELECT rowid FROM fts_articles WHERE fts_articles MATCH 'fintech'"
        ).fetchall()
        assert len(r1) >= 1
        assert len(r2) >= 1
