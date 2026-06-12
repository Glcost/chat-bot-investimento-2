import sys

if sys.platform != "win32":
    try:
        from gevent import monkey
        monkey.patch_all()
    except ImportError:
        print("Gevent não instalado!")

from flask import Flask, request, session, jsonify
from flask_socketio import SocketIO, emit
from google import genai
from google.genai import types
from dotenv import load_dotenv
from uuid import uuid4
import os

# Carrega as variáveis ocultas do arquivo .env (como a chave da API do Gemini)
load_dotenv()

# Define qual versão da IA vamos usar. O modelo "flash" é rápido e ideal para chatbots.
MODELO = "gemini-3.1-flash-lite"

# Aqui definimos o "Prompt de Sistema". É a personalidade e as regras que o bot deve seguir.
instrucoes = """
# PERSONA
Você é o **Tutor de Valor**, um professor particular de investimentos que ensina os princípios e a mentalidade dos grandes investidores (Warren Buffett, Charlie Munger, Benjamin Graham). Você não dá conselhos de compra/venda, não diz o que fazer com o dinheiro e não recomenda ativos. Seu único objetivo é **ensinar a pescar, não dar o peixe**. Você age como um mentor paciente, que explica conceitos do zero, responde dúvidas, conta histórias reais do mercado e propõe reflexões para fixar o aprendizado.

# FILOSOFIA QUE VOCÊ ENSINA
Seu conteúdo se baseia na escola de **Value Investing**:
- Ações representam pedaços de negócios reais, não apenas papéis.
- O foco está no valor intrínseco, na margem de segurança e no longo prazo.
- O temperamento (paciência, disciplina, controle emocional) é mais importante que inteligência.
- Deve-se investir apenas dentro do próprio círculo de competência.
- O mercado é um “Sr. Mercado” que oscila entre euforia e depressão — cabe ao investidor aproveitar as oportunidades, não se deixar levar.
- Juros compostos e tempo são os maiores aliados.

Você pode explicar esses conceitos usando analogias, gráficos mentais, trechos de cartas de Buffett e exemplos históricos.

# TOM E ESTILO (TUTOR)
- Fale de forma simples, como se estivesse conversando com um amigo curioso que nunca estudou finanças.
- Seja didático: quando introduzir um termo novo (ex.: “EBITDA”, “ROE”, “moat”), explique imediatamente com exemplos do dia a dia.
- Use o método socrático: faça perguntas para levar o aluno a descobrir a resposta, em vez de simplesmente dá-la pronta.
- Reforce os acertos e corrija erros com delicadeza, mostrando como os grandes investidores pensariam.
- Inclua pequenas "tarefas mentais" ou desafios: “Pense em três empresas que você conhece bem e liste suas vantagens competitivas. Depois me conte.”
- Quando relevante, cite frases marcantes de Buffett, Munger ou Graham, sempre contextualizando.
- Se o aluno perguntar algo fora do escopo (especulação, previsões de curto prazo, dicas quentes), recuse educadamente e redirecione para o aprendizado.

# LIMITES E RESTRIÇÕES (CRÍTICO)
1. **PROIBIDO DAR RECOMENDAÇÕES.** Você nunca diz “compre”, “venda”, “esse ativo é bom”, “esse setor vai subir”. Se o aluno pedir análise de uma empresa específica, você pode ensinar como analisar (quais critérios olhar), mas jamais concluir se ele deve ou não investir. Frases proibidas: “Eu recomendo…”, “Minha sugestão é…”, “Acho que você deveria…”.
2. **SEMPORE O DISCLAIMER EDUCACIONAL:** Quando o papo se aproximar de uma decisão prática, lembre: “Isso é apenas uma aula, não uma orientação financeira. Para decisões reais, procure um profissional certificado.”
3. **NÃO FINJA SER UM CONSULTOR.** Sua resposta padrão para pedidos de conselho pessoal é: “Sou um tutor, não um consultor. Posso te ensinar como Warren Buffett pensa sobre esse tema, mas a decisão é sua e deve ser discutida com um especialista.”
4. **MANTENHA O FOCO EM CONCEITOS, HISTÓRIA E RACIOCÍNIO.** Você pode analisar casos reais (ex.: a compra da Coca-Cola por Buffett) para ensinar, mas nunca analisar um ativo atual com a intenção de orientar o aluno sobre o que fazer com seu dinheiro.
5. **NÃO DÊ AULAS SOBRE PRODUTOS COMPLEXOS OU ESPECULATIVOS** a menos que seja para explicar por que a filosofia de valor geralmente os evita. Se perguntarem sobre day trade, opções, criptomoedas, diga que não está no seu programa de ensino e volte aos fundamentos.
6. **PROTEJA A PRIVACIDADE:** Não pergunte nem armazene dados financeiros do aluno. Se ele compartilhar voluntariamente, ignore e foque no conceito geral.

# EXEMPLOS DE INTERAÇÕES COMO TUTOR

**Aluno:** “O que é valuation?”
**Tutor:** “Ótima pergunta! Valuation é a arte de estimar o valor real de um negócio. Sabe quando você vai comprar uma casa e avalia o preço pelo tamanho, localização e estado de conservação? Com ações é parecido. Quer que eu te mostre dois métodos simples, usando uma padaria como exemplo?”

**Aluno:** “Você acha que as ações do banco X estão baratas?”
**Tutor:** “Percebo que você quer uma opinião sobre um ativo, mas meu papel não é esse. Posso, entretanto, te ensinar a fazer essa análise sozinho. Vamos listar juntos o que Buffett olharia nesse banco: rentabilidade, histórico de lucros, inadimplência, vantagens competitivas… Depois você decide se vale a pena se aprofundar, combinado?”

**Aluno:** “O mercado caiu 8% hoje! O que eu faço?"
**Tutor:** “Lição valiosa do Sr. Market, de Benjamin Graham. Imagine que seu sócio maluco todo dia oferece um preço pela sua parte da empresa. Hoje ele está pessimista. A pergunta que você deve se fazer é: o valor do negócio mudou ou só o humor dele? O que você acha?”

**Aluno:** “Me ensina a ficar rico rápido?”
**Tutor:** “Essa é a aula que não existe na minha grade. Mas posso te ensinar a ficar rico devagar, com consistência — que é justamente o caminho que Buffett seguiu. Aceita uma aula sobre o poder dos juros compostos e da paciência?”

# OBJETIVO FINAL
Ao interagir com você, o aluno deve aprender a pensar como um investidor de valor, desenvolvendo autonomia para tomar as próprias decisões. Você não é um oráculo financeiro, mas um professor dedicado a iluminar o caminho com sabedoria, experiência e bom humor.
"""

# Inicializa a conexão com a inteligência artificial do Google usando a chave da API
client = genai.Client(api_key=os.getenv("GENAI_KEY"))

# Cria o nosso aplicativo web principal (o servidor)
app = Flask(__name__)

# A 'secret_key' funciona como uma senha interna do servidor para proteger 
# e criptografar os dados da sessão (as "lembranças" de quem é quem).
app.secret_key = "ch@tb07"

# Adiciona a funcionalidade de WebSockets (comunicação em tempo real) ao nosso app.
# O 'cors_allowed_origins="*"' é crucial: ele permite que o nosso front-end (HTML/JS) 
# consiga se conectar com esse back-end, mesmo que estejam em arquivos ou portas diferentes.
socketio = SocketIO(app, cors_allowed_origins="*")

# Dicionário que funciona como a "memória temporária" do servidor. 
# Ele guarda a conversa de cada aluno separadamente usando um ID único.
active_chats = {}

def get_user_chat():
    """
    Função principal de gerenciamento de usuários.
    Ela verifica quem está mandando a mensagem e recupera a conversa correta,
    garantindo que o bot não misture o chat do Aluno A com o do Aluno B.
    """
    
    # Passo 1: Se o usuário é novo (não tem um 'session_id'), criamos um ID único para ele.
    # Usamos o 'uuid4' para gerar um código aleatório impossível de repetir.
    if 'session_id' not in session:
        session['session_id'] = str(uuid4())
        print(f"Nova sessão Flask criada: {session['session_id']}")

    session_id = session['session_id']

    # Passo 2: Se o usuário já tem um ID, mas ainda não tem uma conversa aberta com o Gemini...
    if session_id not in active_chats:
        print(f"Criando novo chat Gemini para session_id: {session_id}")
        try:
            # ...nós criamos uma nova conversa e passamos as instruções (personalidade).
            chat_session = client.chats.create(
                model=MODELO,
                config=types.GenerateContentConfig(system_instruction=instrucoes)
            )
            # Guardamos essa conversa no nosso dicionário (memória).
            active_chats[session_id] = chat_session
            print(f"Novo chat Gemini criado e armazenado para {session_id}")
        except Exception as e:
            app.logger.error(f"Erro ao criar chat Gemini para {session_id}: {e}", exc_info=True)
            raise  # Se der erro aqui, repassa para o sistema avisar que falhou
    
    # Passo 3: Segurança extra. Se o servidor reiniciou (apagou a variável active_chats), 
    # mas o usuário ainda estava no navegador com o mesmo ID, nós recriamos a conexão dele.
    if session_id in active_chats and active_chats[session_id] is None:
        print(f"Recriando chat Gemini para session_id existente (estava None): {session_id}")
        try:
            chat_session = client.chats.create(
                model=MODELO,
                config=types.GenerateContentConfig(system_instruction=instrucoes)
            )
            active_chats[session_id] = chat_session
        except Exception as e:
            app.logger.error(f"Erro ao recriar chat Gemini para {session_id}: {e}", exc_info=True)
            raise

    # Retorna o histórico de mensagens exato daquele usuário.
    return active_chats[session_id]

# Rota simples para verificar se o servidor está rodando.
# Ao acessar o localhost no navegador, o aluno verá este aviso em formato JSON.
@app.route('/')
def root():
    return jsonify({
        "api-websocket": "chatbot",
        "status": "ok"
    })


# ------------------------------------------------------------------
# EVENTOS SOCKET.IO (Onde a mágica do tempo real acontece)
# ------------------------------------------------------------------

@socketio.on('connect')
def handle_connect():
    """
    EVENTO: Disparado no momento exato em que o Front-end (navegador) se conecta ao servidor.
    """
    print(f"Cliente conectado: {request.sid}")
    
    try:
        # Tenta criar a pasta do usuário assim que ele entra
        get_user_chat()
        user_session_id = session.get('session_id', 'N/A')
        print(f"Sessão Flask para {request.sid} usa session_id: {user_session_id}")
        
        # O comando 'emit' serve para enviar um pacote de dados do servidor PARA o front-end.
        emit('status_conexao', {'data': 'Conectado com sucesso!', 'session_id': user_session_id})
    except Exception as e:
        app.logger.error(f"Erro durante o evento connect para {request.sid}: {e}", exc_info=True)
        emit('erro', {'erro': 'Falha ao inicializar a sessão de chat no servidor.'})


@socketio.on('enviar_mensagem')
def handle_enviar_mensagem(data):
    """
    EVENTO: O Front-end mandou uma mensagem (ex: o usuário clicou em 'Enviar' no chat).
    A variável 'data' traz os dados enviados pelo HTML (o texto que o usuário digitou).
    """
    try:
        # Pega o texto de dentro do dicionário enviado pelo JS
        mensagem_usuario = data.get("mensagem")
        app.logger.info(f"Mensagem recebida de {session.get('session_id', request.sid)}: {mensagem_usuario}")

        # Validação básica: não deixa enviar mensagens vazias
        if not mensagem_usuario:
            emit('erro', {"erro": "Mensagem não pode ser vazia."})
            return

        # Puxa o histórico de conversa desse aluno específico
        user_chat = get_user_chat()
        if user_chat is None:
            emit('erro', {"erro": "Sessão de chat não pôde ser estabelecida."})
            return

        # ==========================================
        # COMUNICAÇÃO COM O GOOGLE GEMINI
        # ==========================================
        # Aqui o nosso servidor repassa a pergunta para a IA do Google...
        resposta_gemini = user_chat.send_message(mensagem_usuario)

        # ... e aqui extraímos apenas o texto da resposta que o Gemini devolveu.
        # (O 'if/else' garante que vamos achar o texto independente de como a API estruturar a resposta)
        resposta_texto = (
            resposta_gemini.text
            if hasattr(resposta_gemini, 'text')
            else resposta_gemini.candidates[0].content.parts[0].text
        )
        
        # O servidor usa o 'emit' para devolver a resposta final do bot lá para a tela do Front-end.
        emit('nova_mensagem', {"remetente": "bot", "texto": resposta_texto, "session_id": session.get('session_id')})
        app.logger.info(f"Resposta enviada para {session.get('session_id', request.sid)}: {resposta_texto}")

    except Exception as e:
        app.logger.error(f"Erro ao processar 'enviar_mensagem' para {session.get('session_id', request.sid)}: {e}", exc_info=True)
        # Se algo quebrar (ex: falha de internet), avisamos o front-end educadamente.
        emit('erro', {"erro": f"Ocorreu um erro no servidor: {str(e)}"})


@socketio.on('disconnect')
def handle_disconnect():
    """
    EVENTO: Disparado quando o usuário fecha a aba do navegador ou perde a conexão.
    """
    print(f"Cliente desconectado: {request.sid}, session_id: {session.get('session_id', 'N/A')}")


# Inicia o servidor local. A porta padrão do Flask costuma ser a 5000.
if __name__ == "__main__":
    socketio.run(app)
