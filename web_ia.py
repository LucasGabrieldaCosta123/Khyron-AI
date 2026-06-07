from flask import Flask, render_template, request, jsonify, Response, stream_with_context # type: ignore[reportMissingImports]
import os
import ollama # type: ignore
import time # Importado para simular o tempo de pesquisa

# Tentamos importar o Groq e a Busca
try:
    from groq import Groq #type: ignore
except ImportError:
    Groq = None

try:
    from duckduckgo_search import DDGS #type: ignore
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
    """Faz buscas na web com múltiplas tentativas e fallback para G1/Notícias."""
    if not DDGS:
        return "Erro: Biblioteca de busca não instalada."

    queries = query.split('|')
    todos_resultados = []

    try:
        with DDGS() as ddgs:
            for q in queries:
                q = q.strip()
                # Tentativa 1: Busca normal com região Brasil para maior precisão
                try:
                    res = [r for r in ddgs.text(q, region='br-pt', max_results=5)]
                    if res:
                        todos_resultados.extend(res)
                except:
                    pass

                # Tentativa 2: Se for notícia, tenta forçar fontes confiáveis
                if not todos_resultados and ("notícia" in q.lower() or "bolsa família" in q.lower() or "futebol" in q.lower()):
                    try:
                        res_especifica = [r for r in ddgs.text(f"{q} site:g1.globo.com", region='br-pt', max_results=5)]
                        todos_resultados.extend(res_especifica)
                    except:
                        pass

            if not todos_resultados:
                return "" # Retorna vazio em vez de uma frase que a IA possa repetir

            vistos = set()
            resultados_unicos = []
            for r in todos_resultados:
                if r['href'] not in vistos:
                    vistos.add(r['href'])
                    resultados_unicos.append(r)

            contexto_web = "\n".join([f"Resultado {i+1}: {r['body']}" for i, r in enumerate(resultados_unicos[:15])])
            return contexto_web
    except Exception as e:
        print(f"❌ Erro na pesquisa web: {e}")
        return ""

def otimizar_query(pergunta):
    """Transforma a pergunta do usuário em queries de busca eficientes, evitando datas futuras que quebram a busca."""
    if usar_nuvem():
        try:
            prompt = (
                f"Você é um especialista em SEO. Converta a pergunta do usuário em 2 queries de busca curtas e eficazes para o DuckDuckGo, separadas por '|'. "
                f"Use termos naturais. NÃO force anos como '2026' a menos que o usuário tenha pedido especificamente. "
                f"Se for sobre 'Bolsa Família', use 'Bolsa Família notícias Brasil'. "
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
    username = dados.get('username', 'usuário')

    def generate():
        try:
            # 1. Verifica se precisa de busca na web
            contexto_extra = ""
            precisou = False
            if precisa_de_busca(pergunta):
                query_otimizada = otimizar_query(pergunta)
                time.sleep(3.0)
                resultados_web = pesquisar_web(query_otimizada)
                if resultados_web: # Só adiciona se realmente encontrou algo
                    contexto_extra = f"\n\n--- RESULTADOS DA WEB (Baseados na busca: {query_otimizada}) ---\n{resultados_web}\n-------------------------"
                    precisou = True

            # Sinaliza para o frontend que está pesquisando
            if precisou:
                yield "[SEARCHING]"

            # 2. Prepara as mensagens para a IA
            conhecimento = carregar_conhecimento()
            system_prompt = (
                f"Você é o Khyron, um assistente direto, amigável e ultra-preciso. "
                f"Data e hora atual do usuário: {local_datetime}. "
                f"PERSONALIDADE: Seja natural. Não use frases robóticas. Converse como um amigo inteligente. "
                f"Se o usuário disser 'Olá', responda apenas: 'Olá, {username}, com o que posso te ajudar hoje?'\n\n"
                f"BASE DE DADOS INTERNA (SÓ USE SE FOR RELEVANTE): \n{conhecimento}\n\n"
                f"REGRA CRÍTICA: Nunca mencione tópicos da sua Base de Dados Interna (como Poppy Playtime ou TADC) a menos que o usuário tenha perguntado explicitamente sobre eles ou que seja extremamente pertinente ao assunto. Se você não encontrar a resposta nos resultados da web nem na base interna, diga honestamente que não sabe, mas NÃO tente 'encher linguiça' sugerindo tópicos irrelevantes."
            )
            if contexto_extra:
                system_prompt += (
                    f"\n\nIMPORTANTE: O usuário fez uma pergunta que exigiu busca na web. "
                    f"Use os resultados abaixo para responder. Ignore resultados irrelevantes. "
                    f"Sempre extraia FATOS, datas e nomes. Seja direto e informativo.\n{contexto_extra}"
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
