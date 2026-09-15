import os
import sys

from tecdoc import TecDocAutomator

CODIGO = sys.argv[1] if len(sys.argv) > 1 else "LR164029"
USUARIO = os.environ.get("TECDOC_USER") or input("Usuário do TecDoc: ")
SENHA = os.environ.get("TECDOC_PASS")
if not SENHA:
    SENHA = input("Senha do TecDoc: ")
MARCAS = [m.strip() for m in
          os.environ.get("TECDOC_BRANDS", "Febi,Bosch,SKF,Bilstein").split(",")]
HEADLESS = os.environ.get("TECDOC_HEADLESS", "0") == "1"


def msg(m):
    print("  ", m, flush=True)


auto = TecDocAutomator(USUARIO, SENHA, headless=HEADLESS,
                       marcas=MARCAS, on_mensagem=msg)
try:
    auto.iniciar()
    auto.garantir_login()
    res = auto._buscar_com_reconexao(CODIGO)
    print("\n=== RESULTADO ===")
    for k, v in vars(res).items():
        if k.startswith("_") or v in (None, "", []):
            continue
        print(f"  {k}: {str(v)[:200]}")
finally:
    auto.encerrar()