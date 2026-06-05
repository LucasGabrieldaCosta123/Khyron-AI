from flask import Flask, render_template, request, jsonify, Response, stream_with_context # type: ignore[reportMissingImports]
import re
import os
import json
import ollama # type: ignore

app = Flask(__name__)

# Configuração do Modelo (lucassg_12 está correto!)
MODELO_IA = 'lucassg_12/khyron'

# Configuração para produção (Vercel) e Local
# OLLAMA_HOST deve ser configurado nas Environment Variables da Vercel
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")

headers = {}
if OLLAMA_API_KEY:
    headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

# Adicionado um timeout de 60 segundos. Modelos na nuvem (como o Gemma 31B) 
# podem levar algum tempo para processar o contexto inicial.
client = ollama.Client(host=OLLAMA_HOST, headers=headers, timeout=60.0)

# --- LÓGICA DE DETECÇÃO DE MODELO ---
# Se o host for local ou um túnel (ngrok), usamos o nome curto. 
# Caso contrário (nuvem real), usamos o nome completo.
is_local = any(x in OLLAMA_HOST for x in ["localhost", "127.0.0.1", "ngrok"])
MODELO_ATIVO = 'khyron' if is_local else MODELO_IA

# --- Rotas do Site ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    # Silencia o erro 404 de favicon no console do navegador
    return Response(status=204)

@app.route('/gerar_titulo', methods=['POST'])
def gerar_titulo():
    texto = request.json.get('texto', '')
    prompt = f"Resuma a frase em um título de 2 ou 3 palavras. NÃO use aspas, pontos ou emojis. Responda APENAS as palavras do título: '{texto}'"
    try:
        res = client.chat(model=MODELO_ATIVO, messages=[{'role': 'user', 'content': prompt}], options={'num_predict': 10})
        titulo = res['message']['content'].strip()
        return jsonify({"titulo": titulo})
    except ollama.ResponseError as e:
        print(f"❌ Erro do Ollama ao gerar título: {e.error} (Status: {e.status_code})")
        return jsonify({"titulo": "Erro: Modelo não encontrado", "error": str(e)}), e.status_code
    except Exception as e:
        print(f"❌ Erro inesperado ao gerar título: {str(e)}")
        return jsonify({"titulo": "Erro de Conexão", "error": str(e)}), 500

@app.route('/perguntar', methods=['POST'])
def perguntar():
    dados = request.json
    pergunta = dados.get('texto', '')
    historico = dados.get('historico', [])

    def generate():
        try:
            # Constrói o contexto com o histórico enviado pelo navegador
            mensagens_contexto = [{'role': m['role'], 'content': m['content']} for m in historico]
            
            # Adiciona a pergunta atual
            mensagens_contexto.append({'role': 'user', 'content': pergunta})

            for chunk in client.chat(model=MODELO_ATIVO, messages=mensagens_contexto, stream=True):
                yield chunk['message']['content']
        except ollama.ResponseError as e:
            yield f"❌ Erro do Servidor Ollama: {e.error} (Status: {e.status_code}). "
            if e.status_code == 404:
                yield f"O modelo '{MODELO_ATIVO}' não foi encontrado. Verifique se o nome está correto ou se você fez 'ollama pull'."
        except Exception as e:
            yield f"❌ Erro de Conexão/Rede: {type(e).__name__} - {str(e)}"
    
    return Response(stream_with_context(generate()), mimetype='text/plain')

# Necessário para Vercel encontrar o app na raiz
app_handler = app

if __name__ == '__main__':
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\nSaindo graciosamente...")