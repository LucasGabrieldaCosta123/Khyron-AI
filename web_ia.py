from flask import Flask, render_template, request, jsonify, Response, stream_with_context # type: ignore[reportMissingImports]
import os
import ollama # type: ignore

# Tentamos importar o Groq. Se não estiver instalado, o código não quebra.
try:
    from groq import Groq
except ImportError:
    Groq = None

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
# 1. Groq (Nuvem) - Configure GROQ_API_KEY nas variáveis de ambiente do Vercel
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODELO_NUVEM = "llama-3.3-70b-versatile" # Modelo ultra rápido e potente do Groq

# 2. Ollama (Local)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").strip().rstrip('/')
MODELO_LOCAL = "khyron" # Seu modelo local

# Inicialização dos clientes
groq_client = Groq(api_key=GROQ_API_KEY) if (GROQ_API_KEY and Groq) else None
ollama_client = ollama.Client(host=OLLAMA_HOST, timeout=60.0)

def carregar_conhecimento():
    """Lê o arquivo de conhecimento para atualizar a IA."""
    try:
        with open("knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"⚠️ Não foi possível carregar knowledge.txt: {e}")
        return ""

def usar_nuvem():
    """Verifica se deve usar a nuvem (Groq) ou o Ollama local."""
    return GROQ_API_KEY is not None and groq_client is not None

# --- Rotas do Site ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return Response(status=204)

@app.route('/gerar_titulo', methods=['POST'])
def gerar_titulo():
    texto = request.json.get('texto', '')
    conhecimento = carregar_conhecimento()
    prompt = f"Informações Atualizadas: {conhecimento}\n\nTarefa: Resuma a frase em um título de 2 ou 3 palavras. NÃO use aspas, pontos ou emojis. Responda APENAS as palavras do título: '{texto}'"

    try:
        if usar_nuvem():
            # Chamada para Groq (Nuvem)
            completion = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=MODELO_NUVEM,
                max_tokens=10
            )
            titulo = completion.choices[0].message.content.strip()
        else:
            # Chamada para Ollama (Local)
            res = ollama_client.chat(model=MODELO_LOCAL, messages=[{'role': 'user', 'content': prompt}])
            titulo = res['message']['content'].strip()

        return jsonify({"titulo": titulo})
    except Exception as e:
        print(f"❌ Erro ao gerar título: {str(e)}")
        return jsonify({"titulo": "Erro", "error": str(e)}), 500

@app.route('/perguntar', methods=['POST'])
def perguntar():
    dados = request.json
    pergunta = dados.get('texto', '')
    historico = dados.get('historico', [])
    local_datetime = dados.get('local_datetime', 'Não informada')

    def generate():
        try:
            # Prepara as mensagens para a IA
            conhecimento = carregar_conhecimento()
            mensagens = [{'role': 'system', 'content': f"Você é a IA Khyron. Data e hora atual do usuário: {local_datetime}. Use as seguintes informações atualizadas para responder com precisão: {conhecimento}"}]
            mensagens += [{'role': m['role'], 'content': m['content']} for m in historico]
            mensagens.append({'role': 'user', 'content': pergunta})

            if usar_nuvem():
                # Stream via Groq (Nuvem)
                stream = groq_client.chat.completions.create(
                    messages=mensagens,
                    model=MODELO_NUVEM,
                    stream=True
                )
                for chunk in stream:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield content
            else:
                # Stream via Ollama (Local)
                for chunk in ollama_client.chat(model=MODELO_LOCAL, messages=mensagens, stream=True):
                    yield chunk['message']['content']

        except Exception as e:
            yield f"❌ Erro na conexão: {str(e)}"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
