from flask import Flask, render_template, request, jsonify, Response, stream_with_context # type: ignore[reportMissingImports]
import os
import ollama # type: ignore

# Tentamos importar o Groq e a Busca
try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

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

def usar_nuvem():
    """Verifica se deve usar a nuvem (Groq) ou o Ollama local."""
    return GROQ_API_KEY is not None and groq_client is not None

def carregar_conhecimento():
    """Lê o arquivo de conhecimento para atualizar a IA."""
    try:
        with open("knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"⚠️ Não foi possível carregar knowledge.txt: {e}")
        return ""

# --- FUNÇÕES DE BUSCA WEB ---
def pesquisar_web(query):
    """Faz uma busca no DuckDuckGo e retorna os resumos dos resultados."""
    if not DDGS:
        return "Erro: Biblioteca de busca não instalada."

    try:
        with DDGS() as ddgs:
            # Aumentamos para 10 resultados para ter mais precisão e contexto
            results = [r for r in ddgs.text(query, max_results=10)]
            if not results:
                return "Nenhum resultado relevante encontrado na web."

            contexto_web = "\n".join([f"Resultado {i+1}: {r['body']}" for i, r in enumerate(results)])
            return contexto_web
    except Exception as e:
        print(f"❌ Erro na pesquisa web: {e}")
        return f"Erro ao pesquisar na web: {str(e)}"

def otimizar_query(pergunta):
    """Transforma a pergunta do usuário em uma query de busca profissional e ultra-específica."""
    if usar_nuvem():
        try:
            # Prompt aprimorado para evitar termos ambíguos (como "bolsa" = stock market)
            # e forçar a busca por fatos recentes e específicos.
            prompt = (
                f"Você é um especialista em SEO e buscas. Transforme a pergunta do usuário em 2 ou 3 queries de busca "
                f"curtas, separadas por '|', que tragam os resultados mais precisos e ATUAIS no DuckDuckGo. "
                f"Sempre adicione termos como 'notícias', 'atualizações', 'hoje' ou '2026' se for o caso. "
                f"Se o termo for 'Bolsa Família', especifique 'programa social Brasil' para evitar resultados de bolsa de valores. "
                f"Pergunta: '{pergunta}'. Responda APENAS as queries, sem aspas."
            )
            res = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=MODELO_NUVEM,
                max_tokens=40
            )
            return res.choices[0].message.content.strip()
        except:
            pass
    return pergunta

def precisa_de_busca(pergunta):
    """Analisa se a pergunta exige informações em tempo real ou externas."""
    palavras_chave = ['quem é', 'o que é', 'notícias', 'hoje', 'ontem', 'clima', 'previsão', 'resultado', 'ganhou', 'preço de', 'atual', 'onde está', 'como está']
    if any(word in pergunta.lower() for word in palavras_chave):
        return True

    if usar_nuvem():
        try:
            prompt_decisao = f"Analise a pergunta: '{pergunta}'. Ela exige fatos externos ou notícias recentes? Responda APENAS 'SIM' ou 'NÃO'."
            res = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt_decisao}],
                model=MODELO_NUVEM,
                max_tokens=5
            )
            return "SIM" in res.choices[0].message.content.upper()
        except:
            return False

    return False

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
    prompt = f"Resuma a frase em um título de 2 ou 3 palavras. NÃO use aspas, pontos ou emojis. Responda APENAS as palavras do título: '{texto}'"

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
            # 1. Verifica se precisa de busca na web
            contexto_extra = ""
            precisou = False
            if precisa_de_busca(pergunta):
                # Otimiza a query para obter melhores resultados
                query_otimizada = otimizar_query(pergunta)
                resultados_web = pesquisar_web(query_otimizada)
                contexto_extra = f"\n\n--- RESULTADOS DA WEB (Baseados na busca: {query_otimizada}) ---\n{resultados_web}\n-------------------------"
                precisou = True

            # Sinaliza para o frontend que está pesquisando
            if precisou:
                yield "[SEARCHING]"

            # 2. Prepara as mensagens para a IA
            conhecimento = carregar_conhecimento()
            system_prompt = (
                f"Você é a IA Khyron, um assistente ultra-preciso. Data e hora atual do usuário: {local_datetime}. "
                f"Use as seguintes informações atualizadas para responder com precisão: {conhecimento}"
            )
            if contexto_extra:
                system_prompt += (
                    f"\n\nIMPORTANTE: O usuário fez uma pergunta que exigiu busca na web. "
                    f"Abaixo estão os fatos reais extraídos da internet. "
                    f"Você DEVE ignorar qualquer resultado irrelevante (por exemplo, se a busca for sobre o programa 'Bolsa Família' e o resultado for sobre 'Bolsa de Valores', ignore-o). "
                    f"Extraia as notícias REAIS, fatos, datas e nomes. Não diga apenas que 'existem notícias', diga QUAIS são as notícias. "
                    f"Seja direto, informativo e detalhado. Se não houver fatos concretos nos resultados, admita, mas tente extrair o máximo possível.\n{contexto_extra}"
                )

            mensagens = [{'role': 'system', 'content': system_prompt}]
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
