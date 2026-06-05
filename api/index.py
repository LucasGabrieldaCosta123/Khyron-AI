from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import re
import os
import json
import ollama

# O endereço (Host) é necessário para a Vercel saber para onde enviar a pergunta.
# Se você não tem um host específico, verifique no site onde você pegou a Key
# qual é a "Base URL" ou "API Endpoint" deles.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "https://api.ollama.com")

# A Key funciona como sua identidade/senha para o serviço.
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")

headers = {}
if OLLAMA_API_KEY:
    # A maioria dos provedores exige a Key no cabeçalho de Autorização
    headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

client = ollama.Client(host=OLLAMA_HOST, headers=headers)

# Define caminhos absolutos para garantir que a Vercel encontre os templates fora da pasta api/
base_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(base_dir, '..', 'templates')
static_dir = os.path.join(base_dir, '..', 'static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/perguntar', methods=['POST'])
def perguntar():
    dados = request.json
    pergunta = dados.get('texto', '')
    historico = dados.get('historico', [])

    def generate():
        try:
            mensagens_contexto = [{'role': m['role'], 'content': m['content']} for m in historico]
            mensagens_contexto.append({'role': 'user', 'content': pergunta})
            # Removido o loop duplicado e configurado para usar o modelo 'khyron'
            # Isso garante que as instruções do seu Modelfile sejam respeitadas
            for chunk in client.chat(model='lucassg_12/khyron', messages=mensagens_contexto, stream=True):
                yield chunk['message']['content']
        except Exception as e:
            yield f"Erro: {str(e)}"
    
    return Response(stream_with_context(generate()), mimetype='text/plain')

# Para a Vercel, o app precisa ser exportado
handler = app