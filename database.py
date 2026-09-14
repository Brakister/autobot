"""Camada de persistência SQLite para o cadastroauto.

Tabelas:
- configuracoes  : pares chave/valor (credenciais, preferências)
- sessoes        : registra cada execução de busca (corrida)
- pecas          : resultado de cada código buscado
- cross_references : códigos alternativos/equivalências de cada peça
"""
import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path

import config


def _limpar_codigo(txt) -> str:
    """Remove todo whitespace (espaços/tabs/quebras) de um código."""
    if not txt:
        return ""
    return "".join(str(txt).split())


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Cria as tabelas se ainda não existirem."""
    Path(config.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS configuracoes (
                chave   TEXT PRIMARY KEY,
                valor   TEXT
            );

            CREATE TABLE IF NOT EXISTS sessoes (
                id          TEXT PRIMARY KEY,
                criada_em   TEXT NOT NULL,
                codigo_busca TEXT NOT NULL,
                concluida   INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS pecas (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                sessao_id     TEXT NOT NULL REFERENCES sessoes(id),
                codigo        TEXT NOT NULL,
                descricao     TEXT,
                marca         TEXT,
                fornecedor    TEXT,
                disponivel    INTEGER NOT NULL DEFAULT 0,
                url           TEXT,
                observacao    TEXT,
                criada_em     TEXT NOT NULL,
                UNIQUE(sessao_id, codigo)
            );

            CREATE TABLE IF NOT EXISTS cross_references (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                peca_id     INTEGER NOT NULL REFERENCES pecas(id) ON DELETE CASCADE,
                codigo_ref  TEXT NOT NULL,
                marca_ref   TEXT
            );
            """
        )
        colunas = {row[1] for row in conn.execute("PRAGMA table_info(pecas)")}
        if "aplicacoes" not in colunas:
            conn.execute("ALTER TABLE pecas ADD COLUMN aplicacoes TEXT")
        if "codigos_aplicacao" not in colunas:
            conn.execute("ALTER TABLE pecas ADD COLUMN codigos_aplicacao TEXT")

        # limpeza de dados: códigos coletados do site às vezes vêm com espaços
        # internos (ex.: '038 121 011 B'); normaliza removendo todo whitespace.
        for row in conn.execute(
            "SELECT id, codigo_ref FROM cross_references "
            "WHERE codigo_ref LIKE '% %' OR codigo_ref LIKE char(9) || '%'"
        ).fetchall():
            limpo = _limpar_codigo(row["codigo_ref"])
            if limpo != row["codigo_ref"]:
                conn.execute(
                    "UPDATE cross_references SET codigo_ref = ? WHERE id = ?",
                    (limpo, row["id"]),
                )
        for row in conn.execute(
            "SELECT id, codigos_aplicacao FROM pecas "
            "WHERE codigos_aplicacao LIKE '% %'"
        ).fetchall():
            try:
                lista = json.loads(row["codigos_aplicacao"])
            except Exception:
                continue
            limpos = [_limpar_codigo(c) for c in lista]
            conn.execute(
                "UPDATE pecas SET codigos_aplicacao = ? WHERE id = ?",
                (json.dumps(limpos, ensure_ascii=False), row["id"]),
            )


# ---------------------------------------------------------------------------
# configs
# ---------------------------------------------------------------------------

def get_config(chave: str, default: str | None = None) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT valor FROM configuracoes WHERE chave = ?", (chave,)
        ).fetchone()
    return row["valor"] if row else default


def set_config(chave: str, valor: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO configuracoes (chave, valor) VALUES (?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            (chave, valor),
        )


# ---------------------------------------------------------------------------
# sessão (corrida)
# ---------------------------------------------------------------------------

def criar_sessao(codigo_busca: str) -> str:
    """Cria uma nova sessão e devolve o id."""
    sid = uuid.uuid4().hex
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sessoes (id, criada_em, codigo_busca) VALUES (?, ?, ?)",
            (sid, datetime.now().isoformat(), codigo_busca),
        )
    return sid


def concluir_sessao(sid: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE sessoes SET concluida = 1 WHERE id = ?", (sid,))


# ---------------------------------------------------------------------------
# peças
# ---------------------------------------------------------------------------

def salvar_peca(
    sessao_id: str,
    codigo: str,
    descricao: str | None,
    marca: str | None,
    fornecedor: str | None,
    disponivel: bool,
    url: str | None = None,
    observacao: str | None = None,
    cross_refs: list[tuple[str, str | None]] | None = None,
    aplicacoes: list[str] | None = None,
    codigos_aplicacao: list[str] | None = None,
) -> None:
    """Insere (ou atualiza) uma peça e suas cross-references."""
    codigo = _limpar_codigo(codigo)
    if cross_refs:
        cross_refs = [(_limpar_codigo(r), m) for r, m in cross_refs]
    if codigos_aplicacao:
        codigos_aplicacao = [_limpar_codigo(c) for c in codigos_aplicacao]
    with _connect() as conn:
        conn.execute(
                """INSERT INTO pecas
                 (sessao_id, codigo, descricao, marca, fornecedor, disponivel,
                                    url, observacao, aplicacoes, codigos_aplicacao, criada_em)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(sessao_id, codigo) DO UPDATE SET
                 descricao = excluded.descricao,
                 marca = excluded.marca,
                 fornecedor = excluded.fornecedor,
                 disponivel = excluded.disponivel,
                 url = excluded.url,
                 observacao = excluded.observacao,
                 aplicacoes = excluded.aplicacoes,
                 codigos_aplicacao = excluded.codigos_aplicacao
            """,
            (
                sessao_id, codigo, descricao, marca, fornecedor,
                int(bool(disponivel)), url, observacao,
                json.dumps(aplicacoes or [], ensure_ascii=False),
                json.dumps(codigos_aplicacao or [], ensure_ascii=False),
                datetime.now().isoformat(),
            ),
        )
        peca_id = conn.execute(
            "SELECT id FROM pecas WHERE sessao_id = ? AND codigo = ?",
            (sessao_id, codigo),
        ).fetchone()["id"]

        conn.execute("DELETE FROM cross_references WHERE peca_id = ?", (peca_id,))
        if cross_refs:
            conn.executemany(
                "INSERT INTO cross_references (peca_id, codigo_ref, marca_ref) "
                "VALUES (?, ?, ?)",
                [(peca_id, ref, marca) for ref, marca in cross_refs],
            )


def pecas_da_sessao(sessao_id: str) -> list[dict]:
    """Lista todas as peças de uma sessão junto com suas cross-references."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM pecas WHERE sessao_id = ? ORDER BY id", (sessao_id,)
        ).fetchall()
        result = []
        for row in rows:
            refs = conn.execute(
                "SELECT codigo_ref, marca_ref FROM cross_references "
                "WHERE peca_id = ?",
                (row["id"],),
            ).fetchall()
            d = dict(row)
            d["cross_refs"] = [dict(r) for r in refs]
            result.append(d)
    return result


def todas_sessoes() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM pecas p WHERE p.sessao_id = s.id) "
            "AS total_pecas FROM sessoes s ORDER BY criada_em DESC"
        ).fetchall()
    return [dict(r) for r in rows]
