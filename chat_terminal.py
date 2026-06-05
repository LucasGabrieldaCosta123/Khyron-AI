import torch # type: ignore
import torch.nn as nn # type: ignore
import numpy as np # type: ignore
import torch.nn.functional as F # type: ignore
import os # type: ignore
import time # type: ignore
import sys # type: ignore
import spacy # type: ignore
import re # type: ignore

# Carregando modelo spaCy
print("Carregando PLN (spaCy)...")
try:
    nlp = spacy.load("pt_core_news_lg")
except:
    print("⚠️ Modelo spaCy não encontrado. Baixando...")
    os.system("python -m spacy download pt_core_news_lg")
    nlp = spacy.load("pt_core_news_lg")

def carregar_regras():
    regras = {"proibido": [], "negacao": "Não posso fazer isso.", "insistencia": "Por favor, mude de assunto."}
    if os.path.exists('instrucoes.txt'):
        with open('instrucoes.txt', 'r', encoding='utf-8') as f:
            for linha in f:
                if "sobre" in linha.lower(): regras["proibido"] = [p.strip() for p in re.split(r'sobre', linha, flags=re.IGNORECASE)[1].replace(' e ', ',').split(',')]
                elif "responda:" in linha.lower(): regras["negacao"] = linha.split(':', 1)[1].strip()
                elif "carinhosamente:" in linha.lower(): regras["insistencia"] = linha.split(':', 1)[1].strip()
    return regras

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

class MinhaIA(nn.Module):
    def __init__(self, vocab_size, n_hidden=256, n_layers=1, drop_prob=0.0):
        super(MinhaIA, self).__init__()
        self.n_layers = n_layers
        self.n_hidden = n_hidden
        self.embedding = nn.Embedding(vocab_size, n_hidden)
        self.lstm = nn.LSTM(n_hidden, n_hidden, n_layers, dropout=drop_prob, batch_first=True)
        self.dropout = nn.Dropout(drop_prob)
        self.fc = nn.Linear(n_hidden, vocab_size)
      
    def forward(self, x, hidden):
        embeds = self.embedding(x)
        r_output, hidden = self.lstm(embeds, hidden)
        out = self.dropout(r_output)
        out = out.reshape(-1, self.n_hidden)
        out = self.fc(out)
        return out, hidden

    def init_hidden(self, batch_size):
        weight = next(self.parameters()).data
        return (weight.new(self.n_layers, batch_size, self.n_hidden).zero_(),
                weight.new(self.n_layers, batch_size, self.n_hidden).zero_())

def carregar_ia(caminho):
    if not os.path.exists(caminho): return None
    checkpoint = torch.load(caminho, map_location=device)
    net = MinhaIA(len(checkpoint['tokens']), n_hidden=checkpoint['n_hidden'], n_layers=checkpoint['n_layers'])
    net.load_state_dict(checkpoint['state_dict'])
    net.word2int = {w: i for i, w in enumerate(checkpoint['tokens'])}
    net.int2word = {i: w for i, w in enumerate(checkpoint['tokens'])}
    net.to(device).eval()
    return net

def prever(net, word, h, top_k=5, temperature=0.7):
    x = torch.tensor([[net.word2int.get(word, 0)]]).to(device)
    h = tuple([each.data for each in h])
    out, h = net(x, h)
    p = F.softmax(out / max(temperature, 1e-5), dim=1).data.topk(top_k)
    choices = p[1].cpu().numpy().flatten()
    probs = (p[0] / p[0].sum()).cpu().numpy().flatten()
    word = net.int2word[np.random.choice(choices, p=probs)]
    return word, h

def gerar_resposta(net, frase, tamanho=30, temp=0.7, top_k=5):
    h = net.init_hidden(1)
    tokens = re.findall(r"[\w']+|[.,!?;:]", frase.lower())
    
    # Se a frase estiver vazia ou palavras não existirem, começa com um ponto
    word = tokens[0] if tokens else "."
    
    # Alimenta o contexto
    for t in tokens:
        word, h = prever(net, t, h, top_k, temp)
    
    res = [word]
    for _ in range(tamanho):
        word, h = prever(net, res[-1], h, top_k, temp)
        if word == '__h__':
            break
        if word == '\n': break
        res.append(word)
    # Limpeza de pontuação para ficar natural
    texto = " ".join(res).replace(" !", "!").replace(" ?", "?").replace(" .", ".").replace(" ,", ",")
    return texto.strip()

def chat():
    VERDE, CIANO, RESET = '\033[92m', '\033[96m', '\033[0m'
    model = carregar_ia('minha_ia_cerebro.pth')
    if model is None: return print("Erro: Cérebro não encontrado.")
    ultima_foi_negativa = False
    nome_usuario = None

    while True:
        user_input = input(f"{VERDE}Você:{RESET} ")
        if user_input.lower() in ['sair', 'exit', 'tchau']: break
        
        regras = carregar_regras()
        doc = nlp(user_input) # Usamos o texto original para facilitar o NER

        # Tenta identificar o nome do usuário se ainda não souber
        if nome_usuario is None:
            for ent in doc.ents:
                if ent.label_ == "PER":
                    nome_usuario = ent.text
                    break
        
        # 1. Sistema de Regras (Manual de Conduta)
        mencionou = any(t.lemma_ in regras["proibido"] for t in doc if t.text.lower())
        if mencionou:
            print(f"{CIANO}Khyron: {RESET}{regras['insistencia'] if ultima_foi_negativa else regras['negacao']}")
            ultima_foi_negativa = True
            continue
        ultima_foi_negativa = False

        # 2. Verificação de Conhecimento com spaCy (A compreensão real)
        # Criamos um "conhecimento base" para comparar a intenção do usuário
        conhecimento_base = nlp("oi tudo bem quem criou o que faz sol água piada python")
        
        # Verifica se as palavras existem no vocabulário da IA
        palavras_conhecidas = [t.text for t in doc if t.text.lower() in model.word2int]
        conhece = len(palavras_conhecidas) > 0 or doc.similarity(conhecimento_base) > 0.4

        if not conhece:
            print(f"{CIANO}Khyron: {RESET}Ainda não aprendi sobre isso, vamos falar de outra coisa?")
            with open('perguntas_desconhecidas.txt', 'a', encoding='utf-8') as f:
                f.write(f"{user_input}\n")
        else:
            # 3. Geração de Resposta (A fala da IA)
            resp = gerar_resposta(model, f"__h__ {user_input} __i__", 25)
            print(f"{CIANO}Khyron: {RESET}{resp}")

if __name__ == "__main__":
    # Otimização para CPU se necessário
    if device.type == 'cpu':
        torch.set_num_threads(2)
    chat()