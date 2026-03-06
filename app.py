from flask import Flask, render_template
import os

app = Flask(__name__)

# Função para ler seu banco de dados atual
def carregar_dados():
    if not os.path.exists("banco_imoveis.txt"):
        return []
    imoveis = []
    with open("banco_imoveis.txt", "r") as f:
        for line in f:
            d = line.strip().split(";")
            if len(d) >= 11:
                imoveis.append({
                    "uf": d[0],
                    "local": d[1],
                    "tipo": d[2],
                    "valor": d[6],
                    "id": d[10]
                })
    return imoveis[::-1] # Mostra os mais recentes primeiro

@app.route('/')
def home():
    dados = carregar_dados()
    return render_template('index.html', imoveis=dados)

if __name__ == '__main__':
    # No Codespaces, usamos a porta 5000
    app.run(host='0.0.0.0', port=5000, debug=True)