"""Painel local da ementa: lê o ZSRest (só SELECT), gera menu.json e publica."""
import json, subprocess, sys, webbrowser
from datetime import datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BASE = Path(__file__).parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
PUB = BASE / CFG["pasta_publica"]


def ler_produtos():
    import pyodbc
    s = CFG["sql_server"]
    ligacao = (f"DRIVER={{{s['driver']}}};SERVER={s['servidor']};DATABASE={s['base_dados']};"
               f"UID={s['utilizador']};PWD={s['palavra_passe']};TrustServerCertificate=yes")
    sql = CFG["consulta_ementa"].strip()
    if not sql.upper().startswith("SELECT"):
        raise ValueError("Só são permitidas consultas SELECT.")
    with pyodbc.connect(ligacao, timeout=10, readonly=True) as c:
        return c.cursor().execute(sql).fetchall()


def construir_menu(linhas):
    cats = {}
    for categoria, sub, produto, preco in linhas:
        c = cats.setdefault(categoria or "Outros", {})
        c.setdefault(sub or "", []).append(
            {"nome": produto, "preco": float(preco) if isinstance(preco, Decimal) else preco})
    return {
        "nome": CFG["nome_restaurante"],
        "atualizado": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "categorias": [
            {"nome": n, "subcategorias": [{"nome": sn, "produtos": p} for sn, p in subs.items()]}
            for n, subs in cats.items()],
    }


def publicar():
    if not CFG["publicar_com_git"]:
        return "Ficheiro gerado (publicação git desativada)."
    git = lambda *a: subprocess.run(["git", *a], cwd=BASE, capture_output=True, text=True)
    git("add", str(PUB))
    git("commit", "-m", f"Ementa {datetime.now():%Y-%m-%d %H:%M}")
    r = git("push")
    return "Publicado." if r.returncode == 0 else "Erro ao publicar: " + r.stderr


def atualizar():
    menu = construir_menu(ler_produtos())
    (PUB / "menu.json").write_text(json.dumps(menu, ensure_ascii=False, indent=1), encoding="utf-8")
    n = sum(len(s["produtos"]) for c in menu["categorias"] for s in c["subcategorias"])
    return f"{n} produtos lidos. " + publicar()


def listar_tabelas():
    """Mostra tabelas/colunas relevantes para confirmar os nomes usados na consulta."""
    import pyodbc
    s = CFG["sql_server"]
    ligacao = (f"DRIVER={{{s['driver']}}};SERVER={s['servidor']};DATABASE={s['base_dados']};"
               f"UID={s['utilizador']};PWD={s['palavra_passe']};TrustServerCertificate=yes")
    sql = ("SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
           "WHERE TABLE_NAME LIKE '%produto%' OR TABLE_NAME LIKE '%familia%' "
           "ORDER BY TABLE_NAME, ORDINAL_POSITION")
    with pyodbc.connect(ligacao, timeout=10, readonly=True) as c:
        atual = None
        for t, col in c.cursor().execute(sql):
            if t != atual:
                print("\n" + t)
                atual = t
            print("   ", col)


def gerar_qr():
    import qrcode
    qrcode.make(CFG["url_publico"]).save(BASE / "qr_ementa.png")
    print("QR code guardado em qr_ementa.png ->", CFG["url_publico"])


PAGINA = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Painel da ementa</title>
<style>body{font:18px system-ui;max-width:30rem;margin:3rem auto;padding:0 1rem}
button{font:inherit;padding:.8rem 1.4rem;border:0;border-radius:8px;background:#0f5c5c;color:#fff;cursor:pointer}
button:disabled{opacity:.5}#r{margin-top:1.2rem;white-space:pre-wrap}</style>
<h1>Ementa digital</h1><button id=b>Atualizar ementa</button><p id=r></p>
<script>b.onclick=async()=>{b.disabled=true;r.textContent='A atualizar…';
try{r.textContent=await(await fetch('/atualizar',{method:'POST'})).text()}
catch(e){r.textContent='Falha: '+e}b.disabled=false}</script>"""


class Painel(BaseHTTPRequestHandler):
    def _enviar(self, texto, tipo="text/plain", codigo=200):
        self.send_response(codigo)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8")
        self.end_headers()
        self.wfile.write(texto.encode("utf-8"))

    def do_GET(self):
        self._enviar(PAGINA, "text/html")

    def do_POST(self):
        try:
            self._enviar(atualizar())
        except Exception as e:
            self._enviar(f"Erro: {e}", codigo=500)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    if "--tabelas" in sys.argv:
        listar_tabelas()
    elif "--qr" in sys.argv:
        gerar_qr()
    else:
        porta = CFG["porta_painel"]
        print(f"Painel em http://127.0.0.1:{porta}  (Ctrl+C para sair)")
        webbrowser.open(f"http://127.0.0.1:{porta}")
        HTTPServer(("127.0.0.1", porta), Painel).serve_forever()
