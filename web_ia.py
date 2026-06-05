from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import re
import os
import json
import ollama # type: ignore

app = Flask(__name__)

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
        # Alterado de 'gemma4:31b-cloud' para 'khyron'. 
        # Mesmo para títulos, usar o seu modelo customizado é mais consistente.
        res = ollama.chat(model='lucassg_12/khyron', messages=[{'role': 'user', 'content': prompt}], options={'num_predict': 10})
        titulo = res['message']['content'].strip()
        return jsonify({"titulo": titulo})
    except:
        return jsonify({"titulo": texto[:20] + "..."})

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

            for chunk in ollama.chat(model='lucassg_12/khyron', messages=mensagens_contexto, stream=True):
                yield chunk['message']['content']
        except Exception as e:
            yield f"Erro ao conectar com Ollama: {str(e)}"
    
    return Response(stream_with_context(generate()), mimetype='text/plain')


if __name__ == '__main__':
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\nSaindo graciosamente...")