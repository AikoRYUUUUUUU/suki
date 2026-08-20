# Changelog — Suki

Resumo das atualizações de funcionalidades mais recentes do site, mais importantes primeiro dentro de cada seção.

## Cadastro de mangás (admin)

- **Autofill via AniList** — botão "Buscar dados" ao lado do título no formulário de novo mangá. Busca direto no navegador do admin (não passa pelo servidor) e preenche título original, sinopse, ano, status, avaliação, autor/artista e as tags correspondentes. Se não encontrar nada, mostra um aviso vermelho no canto da tela pedindo preenchimento manual; se encontrar só parte dos dados, avisa o que faltou.
- **Painel em cards** — a lista de mangás no `/admin` agora mostra a capa de cada título, em vez de uma lista de texto.
- **Editar mangá existente** — novo botão "Editar" em cada card abre um formulário com todos os dados já preenchidos (título, título original, sinopse, ano, avaliação, artista, tags, autor, grupo) para atualizar sem precisar recriar o cadastro.
- **Status editável direto na lista** — dropdown de status em cada card salva sozinho ao trocar, sem abrir outra tela.
- **Catálogo fixo de 30 tags** — o campo de tags manuais foi substituído por uma seleção de 30 tags fixas, agrupadas em Gêneros, Demografia, Relacionamento (incl. Yaoi/Yuri) e Conteúdo sensível (Ecchi, Smut, Hentai, Adulto 18+, Mature) — esse último grupo tem aviso visual próprio.

## Busca e navegação (site público)

- **Página de busca dedicada** (`/busca.html`) — em vez de filtrar a home, a busca agora leva pra uma página própria com os resultados, com um painel de filtro por tags (incluindo aviso pras tags sensíveis).
- **Busca por múltiplos campos** — nome, autor, grupo, tag/gênero e status, tudo na mesma busca.
- **Link "Biblioteca"** no menu agora leva direto pra página de todos os títulos, em vez da home.
- **Status do mangá fixo** — 3 opções apenas (Em Hiatus, Em andamento, Finalizado), tanto no cadastro quanto no filtro de busca.

## Home

- **Hero rotativo** — a seção de destaque da home troca aleatoriamente entre os mangás do catálogo a cada alguns segundos, mostrando título, sinopse e tags de cada um, com transição suave.
- **Capa em destaque maior** — a capa exibida na hero da home aumentou de tamanho, ficando mais proeminente.

## Classificação de conteúdo

- **Selo "+18" na capa** — mangás marcados com tags adultas (Adulto 18+, Hentai, Smut, Mature) mostram um selo vermelho "+18" ao lado do status, em todas as capas do catálogo.
- **Verificação de idade no leitor** — ao abrir um capítulo de um mangá +18, aparece um popup pedindo a confirmação de maioridade antes de liberar a leitura; quem recusa é levado de volta pra página do mangá.

## Identidade visual

- **Rebrand para "Suki"** — nova logo (símbolo + wordmark desenhados à mão, com o "i" em forma de folha) substituindo o antigo texto "Sumi" em todo o site, incluindo favicon novo.
- **Textura de fundo** — degradê sutil no fundo das páginas e o kanji 好 como marca d'água discreta, dissolvendo no canto da tela (fora da página de leitura, que continua limpa).
- **Selos de status mais legíveis** — o rótulo de status nas capas (Em andamento/Finalizado/etc) ficou mais opaco pra não sumir em cima de capas claras.

## Correções

- Corrigido um bug de CSS em que os campos de tag do admin herdavam o estilo dos rótulos do formulário (texto forçado em maiúsculas, espaçamento exagerado entre linhas).
- Botões de "escolher arquivo" (capa, páginas de capítulo) agora seguem a identidade visual do site em vez do estilo padrão do navegador.

---
*Gerado em 2026-08-20 a partir do histórico de commits do projeto.*
