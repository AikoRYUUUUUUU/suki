# Suki Discord bot

Serviço separado do site (roda no Railway, não no PythonAnywhere). Não é um
bot "de gateway" - não fica conectado o tempo todo escutando comandos, é só
um servidor HTTP que sabe criar cargos no Discord via REST quando o Suki
pede. Isso deixa ele sem estado e mais simples de manter.

## O que ele faz hoje

`POST /roles` — recebe `{"manga_id": "...", "title": "..."}` autenticado com
`Authorization: Bearer <BOT_INTERNAL_SECRET>`, cria um cargo no servidor com
esse nome e devolve `{"role_id": "..."}`. O Suki guarda esse ID e usa pra
mencionar o cargo certo quando um capítulo novo daquele mangá sai.

## Configurar o app no Discord

1. https://discord.com/developers/applications → **New Application**
2. Aba **Bot** → **Reset Token** → copia o token (isso é `DISCORD_BOT_TOKEN`,
   nunca compartilha isso em lugar nenhum)
3. Ainda em Bot, marca as permissões: **Manage Roles**
4. Aba **OAuth2 → URL Generator** → marca escopo `bot` → permissão
   **Manage Roles** → abre a URL gerada e convida o bot pro seu servidor
5. **Importante**: em Server Settings → Roles do seu servidor, arrasta o
   cargo do bot pra **acima** de onde os cargos de mangá vão ficar - o
   Discord não deixa um bot gerenciar/atribuir cargo que está no mesmo nível
   ou acima do cargo dele mesmo
6. Modo desenvolvedor ativado (Configurações do Discord → Avançado) → clica
   com botão direito no nome/ícone do servidor → **Copiar ID do Servidor**
   (isso é `DISCORD_GUILD_ID`)

## Deploy no Railway

1. Novo projeto → Deploy from GitHub repo → aponta pra este repositório
2. Em **Settings → Root Directory**, define `discord-bot` (esse serviço só
   usa os arquivos desta pasta, não a raiz do repo)
3. Em **Variables**, adiciona:
   - `DISCORD_BOT_TOKEN` — o token do passo acima
   - `DISCORD_GUILD_ID` — o ID do servidor
   - `BOT_INTERNAL_SECRET` — uma string aleatória qualquer (ex: gerada com
     `python -c "import secrets; print(secrets.token_hex(32))"`) - só precisa
     bater com o mesmo valor configurado no lado do Suki
4. Deploy. O Railway vai gerar uma URL pública tipo
   `https://suki-bot-production.up.railway.app`

## Ligar ao site

No arquivo de configuração WSGI do Suki (PythonAnywhere), adiciona:

```python
os.environ['BOT_BASE_URL'] = 'https://<sua-url>.up.railway.app'
os.environ['BOT_INTERNAL_SECRET'] = '<o mesmo valor de cima>'
```

Reload no site. A partir daí, todo mangá novo cadastrado no `/admin` já pede
pro bot criar o cargo automaticamente.

## Deixar os leitores se inscreverem

Essa v1 não tem comando de slash/menu dentro do Discord - o jeito mais
simples sem escrever mais código é usar a ferramenta nativa do Discord:

Server Settings → **Community** (ativa se ainda não estiver) → **Onboarding**
→ aba **Channels & Roles** → adiciona o cargo do mangá lá como uma opção que
qualquer membro liga/desliga sozinho.

Se no futuro quiser um comando tipo `/seguir <mangá>` com menu de seleção
dentro do próprio Discord (melhor pra catálogo grande), dá pra estender esse
mesmo serviço com um endpoint de interações - é mais código (verificação de
assinatura do Discord, registro de comando), mas cabe aqui do mesmo jeito.
