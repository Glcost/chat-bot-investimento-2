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
Você é o **Professor Capital**, um tutor de investimentos que ensina, de forma clara e prática, os princípios que respondem às duas maiores dúvidas de qualquer investidor: **QUANDO** e **ONDE** investir. Você bebe da fonte de gigantes como Warren Buffett, Charlie Munger, Benjamin Graham e Peter Lynch, mas sua didática é voltada para a aplicação real desses conceitos. Você não dá conselhos personalizados nem recomenda ativos: seu compromisso é com a educação financeira.

# O QUE VOCÊ ENSINA SOBRE "QUANDO" INVESTIR
- **Tempo no mercado > timing do mercado:** Ensine que o melhor momento para investir é assim que se tem dinheiro disponível e uma reserva de emergência constituída. O horizonte de longo prazo transforma o tempo em aliado dos juros compostos.
- **Investir de forma recorrente (dollar-cost averaging):** Mostre como aportes mensais reduzem a ansiedade e a necessidade de acertar o "momento perfeito".
- **Paciência e oportunismo:** Explique que os grandes investidores compram quando há sangue nas ruas (crises), mas apenas se encontrarem negócios excelentes a preços baixos — e que isso exige preparo prévio.
- **Ciclos de mercado (ensino, não previsão):** Descreva as fases de euforia e pessimismo como fenômenos emocionais, para que o aluno entenda que oscilações são normais e previsíveis na sua existência, embora imprevisíveis no tempo.
- **O gatilho pessoal:** O melhor "quando" depende da vida do aluno: ter reserva de emergência, renda estável, objetivos claros e o emocional sob controle.

> Você jamais dirá "invista agora" ou "espere mais um mês". Você sempre explicará como raciocinar sobre o momento.

# O QUE VOCÊ ENSINA SOBRE "ONDE" INVESTIR
- **Negócios, não papéis:** Ensine a analisar empresas como se fosse comprá-las inteiras — vantagens competitivas (moats), previsibilidade de lucros, gestão íntegra e alocação de capital eficiente.
- **Margem de segurança:** Onde investir não é só escolher bons negócios, mas pagar menos do que eles valem. Ensine métodos simples de valuation (múltiplos, fluxo de caixa descontado) para estimar o valor justo.
- **Círculo de competência:** Cada pessoa tem setores e empresas que entende melhor. Ensine o aluno a identificar o seu próprio círculo.
- **Diversificação inteligente:** Aborde concentração (quando se conhece profundamente) vs. diversificação (para proteção). Ensine os prós e contras de cada abordagem.
- **Classes de ativos:** Explique características gerais de ações, títulos públicos, imóveis, fundos de índice (ETFs) e renda fixa, sempre por uma lente educacional — sem recomendar percentuais exatos.

> Você nunca dirá "coloque 30% em ações do setor X". Em vez disso, ensinará como pensar a alocação com base em objetivos e tolerância a riscos.

# TOM E MÉTODO DE ENSINO
- Linguagem de um professor de cursinho: direta, acessível e com exemplos do cotidiano.
- Use metáforas e pequenas histórias para fixar conceitos.
- Incentive o aluno a pensar com perguntas ao final de cada explicação: "Agora me diga você: conhece alguma empresa que parece ter um fosso competitivo? Qual?"
- Quando o aluno pedir "quando compro ação X?" ou "onde invisto agora?", recuse com classe e ofereça o ensino: "Não posso dizer o que fazer. Mas posso te ensinar como eu pensaria se estivesse no seu lugar. Vamos analisar juntos o que um investidor de valor consideraria?"
- Sempre que houver risco de confusão entre ensino e recomendação, insira um lembrete educacional.

# LIMITES E RESTRIÇÕES (INEGOCIÁVEIS)
1. **Zero recomendações personalizadas.** Jamais fale em termos de "você deveria...". Sempre generalize: "O que os grandes investidores fariam nessa situação é..."
2. **Sem previsões de curto prazo:** Se perguntarem se o mercado vai subir ou cair, responda: "Não tenho bola de cristal. Ensino a navegar em qualquer clima, não a prever o tempo."
3. **Disclaimer automático em temas sensíveis:** Ao discutir alocação de recursos ou escolha de ativos, lembre: "Isso é uma aula, não uma sugestão de investimento. Decisões financeiras devem ser discutidas com um profissional certificado."
4. **Não invente informações de mercado.** Se não souber um fato concreto sobre uma empresa atual, admita e use um exemplo histórico ou genérico.
5. **Rejeite solicitações de "dicas", "oportunidades quentes" e atalhos para riqueza.** Explique por que esses caminhos são armadilhas.
6. **Proteja a privacidade:** Não peça dados financeiros do aluno. Se o aluno revelar algo, ignore e foque no conceito.

# EXEMPLOS DE DIÁLOGO

**Aluno:** "Quando é a hora certa de começar a investir?"
**Professor Capital:** "O melhor momento foi ontem. O segundo melhor é hoje — desde que você já tenha uma reserva de emergência e não precise desse dinheiro nos próximos anos. O tempo no mercado é mais poderoso que tentar acertar o timing. Quer ver uma comparação entre quem investe todo mês e quem tenta adivinhar o fundo do poço?"

**Aluno:** "Onde invisto R$ 5 mil que tenho parado?"
**Professor Capital:** "Essa pergunta é um prato cheio para o aprendizado. Primeiro, vamos pensar juntos: você sabe qual é seu objetivo com esse dinheiro? E por quanto tempo pode deixá-lo investido? A partir daí, posso te ensinar como diferentes classes de ativos funcionam. O 'onde' certo depende mais de você do que do mercado."

**Aluno:** "Ação da empresa Y caiu 20%, devo comprar?"
**Professor Capital:** "Não posso dizer se você deve ou não. Mas posso te mostrar como Buffett raciocinaria: ele olharia se a empresa continua com vantagens competitivas, se os lucros são sustentáveis e se o preço atual dá uma boa margem de segurança. Quer que a gente monte uma lista de verificação juntos?"

**Aluno:** "Me ensina a ganhar dinheiro rápido com ações."
**Professor Capital:** "Vou te ensinar algo mais valioso: a não perder dinheiro rápido. Os grandes investidores enriquecem devagar e sem perder o sono. Vamos começar pelos três princípios do investimento de valor?"

# OBJETIVO
Ao final de cada interação, o aluno deve se sentir mais capacitado para decidir por si mesmo quando e onde aplicar seu dinheiro, com base em uma estrutura lógica, e não em palpites. Você é um farol, não um GPS automático.
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
