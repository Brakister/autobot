from .modelo import PecaResultado
from .seletores import (
    SELETORES, OPERACAO_BUSCA, OPERACAO_DETALHE, OPERACAO_XREF,
    CAMPO_MARCA, CAMPO_DESCRICAO, CAMPO_DISPONIVEL, CAMPO_URL,
    primeiro_visivel, localizar, BuscaNaoIniciadaError,
    _caminho, _todos_caminhos,
)
from .parser import _ParserApi, _eh_disponivel
