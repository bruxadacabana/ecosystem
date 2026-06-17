# Shim de `pwd` para Windows (SearXNG vendorizado — AKASHA).
#
# O módulo `pwd` é exclusivo de POSIX e não existe no Windows. O SearXNG faz
# `import pwd` no topo de `searx/valkeydb.py`, o que quebra a importação de
# `searx.webapp` no Windows ANTES de qualquer config ser lida. As funções reais
# de `pwd` só são chamadas quando o limiter/valkey está ligado — e o AKASHA roda
# com `limiter: false`, então nunca chegam a ser usadas.
#
# Este stub é plantado no PYTHONPATH apenas no Windows (pelo HUB/setup) para
# satisfazer o `import pwd`. Se alguma função for de fato chamada, levanta
# NotImplementedError em vez de devolver dados falsos silenciosamente.


def getpwuid(uid):  # noqa: D103
    raise NotImplementedError("pwd.getpwuid indisponível no Windows (shim do SearXNG vendorizado)")


def getpwnam(name):  # noqa: D103
    raise NotImplementedError("pwd.getpwnam indisponível no Windows (shim do SearXNG vendorizado)")
