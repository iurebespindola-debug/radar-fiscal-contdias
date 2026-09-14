# Fique de olho ⚠ — Contdias

Um painel que reúne, todo dia, as notícias estritamente tributárias mais importantes (Federal, Estadual, Municipal e da Reforma Tributária), com foco especial em Minas Gerais, São Paulo e Rio de Janeiro.

O radar só traz notícias que envolvem **alíquota de imposto, alteração de declarações fiscais/obrigações acessórias, NCM, CFOP, CST, parcelamentos e benefícios fiscais** — assuntos de RH, saúde, eventos e notícias administrativas genéricas ficam de fora automaticamente.

Também tem uma aba **🧾 Consulta ISS**, com alíquota de ISS por município (base do Portal Nacional da NFS-e, gov.br/nfse) e as regras de onde o imposto é devido e se há retenção obrigatória, segundo a LC 116/2003. Essa base é **verificada e atualizada automaticamente todo dia** — o script checa se o governo publicou um arquivo novo e, se sim, já substitui os dados no painel sozinho. Se alguma notícia do dia mencionar a LC 116/2003 (sinal de possível mudança na lei), o boletim por e-mail avisa — mas as regras jurídicas da aba não são reescritas sozinhas, por segurança; nesse caso, alguém revisa e pede pra eu atualizar o texto.

Tem ainda uma aba **🔍 Consulta NCM**: digite o NCM e o painel consulta ao vivo (via uma função do Netlify, em `netlify/functions/consulta-ncm.mjs`) o cClassTrib e o CST IBS/CBS de referência para aquele produto na Reforma Tributária (LC 214/2025 + LC 227/2026), e avisa se é regime geral ou tem redução/benefício. A fonte é o buscadorncm.com.br (agregador especializado, não é fonte oficial do governo) — para benefícios condicionais, sempre confirme se a descrição real do produto se encaixa na condição exigida antes de aplicar. Para conferir uma planilha inteira de produtos de um cliente (com cruzamento de duas fontes e nível de confiança por item), isso continua sendo feito comigo numa conversa, não pelo painel — é um trabalho de análise, não uma consulta simples.

Você recebeu 3 arquivos:

| Arquivo | Para que serve |
|---|---|
| `radar_fiscal_contdias.html` | O painel em si — é o que você abre no navegador |
| `radar_fiscal_scraper.py` | O programinha que busca as notícias e atualiza o painel |
| `README.md` | Este guia |

Mantenha os três arquivos **na mesma pasta**.

---

## 1. Ver o painel agora (sem instalar nada)

Dê dois cliques no arquivo `radar_fiscal_contdias.html`. Ele abre no seu navegador (Chrome, Edge, etc.) e já mostra 3 notícias de **exemplo**, só para você ver como fica. Para trazer notícias de verdade, siga o passo 2.

---

## 2. Instalar o Python (só na primeira vez)

O programinha que busca as notícias precisa do Python instalado no computador (é gratuito).

1. Acesse **python.org/downloads** e baixe a versão para Windows (ou Mac).
2. Instale normalmente. **Importante:** na primeira tela do instalador do Windows, marque a caixinha **"Add Python to PATH"** antes de clicar em Install.
3. Para confirmar que funcionou: abra o **Prompt de Comando** (Windows) ou **Terminal** (Mac) e digite:
   ```
   python --version
   ```
   Se aparecer um número de versão (ex: `Python 3.12.4`), está tudo certo.

Depois, instale duas bibliotecas que o programa usa (só precisa fazer isso uma vez também):

```
pip install requests beautifulsoup4
```

---

## 3. Rodar a coleta de notícias

1. Abra o Prompt de Comando/Terminal.
2. Navegue até a pasta onde estão os 3 arquivos. Exemplo, se estiverem na área de trabalho:
   ```
   cd Desktop
   ```
3. Rode:
   ```
   python radar_fiscal_scraper.py
   ```
4. Aguarde — pode levar de 1 a 3 minutos, porque ele visita várias fontes (Receita Federal, Câmara, CFC, Contábeis e as SEFAZ dos 27 estados).
5. Quando terminar, abra (ou atualize, se já estava aberto) o `radar_fiscal_contdias.html` no navegador. As notícias reais vão substituir as de exemplo.

Se alguma fonte falhar (é normal — sites de governo mudam de endereço de vez em quando), o programa **não trava**: ele mostra `[falhou] Nome da fonte: motivo` na tela, pula aquela fonte e continua as outras normalmente. Se isso acontecer com muita frequência numa fonte específica, me avise que eu ajusto o endereço dela.

---

## 4. Fazer isso rodar sozinho, todo dia às 08h

### Windows (Agendador de Tarefas)

1. No menu Iniciar, procure por **"Agendador de Tarefas"** e abra.
2. Clique em **"Criar Tarefa Básica"**.
3. Nome: `Radar Fiscal Contdias`.
4. Disparador: **Diariamente**, horário **08:00**.
5. Ação: **Iniciar um programa**.
   - Programa/script: caminho completo do Python, por exemplo `C:\Users\SeuUsuario\AppData\Local\Programs\Python\Python312\python.exe`
     (para descobrir o caminho exato, digite `where python` no Prompt de Comando)
   - Argumentos: `radar_fiscal_scraper.py`
   - Iniciar em: a pasta onde estão os 3 arquivos, por exemplo `C:\Users\SeuUsuario\Desktop`
6. Finalizar. Pronto — o painel vai se atualizar sozinho todo dia às 8h (desde que o computador esteja ligado nesse horário).

### Mac / Linux (cron)

1. No Terminal, digite `crontab -e`.
2. Adicione a linha (ajustando o caminho da pasta):
   ```
   0 8 * * * cd /Users/SeuUsuario/Desktop && /usr/bin/python3 radar_fiscal_scraper.py >> radar_log.txt 2>&1
   ```
3. Salve e feche. Pronto.

---

## 5. Painel online (link fixo, sempre atualizado)

O painel também está publicado em:

**https://radar-fiscal-contdias.netlify.app**

Esse link é permanente e se atualiza **sozinho** a cada coleta — não precisa fazer nada. Funciona assim: a cada execução do `radar_fiscal_scraper.py`, o script publica automaticamente uma cópia do painel (`index.html`) no repositório GitHub `radar-fiscal-contdias`, e o Netlify está configurado para publicar sozinho a cada envio (push) para esse repositório.

Se um dia o link parar de atualizar, os pontos para checar são:
1. O computador rodou a coleta hoje? (veja o Agendador de Tarefas)
2. O Git está autenticado? Rode `git push` manualmente na pasta do projeto — se pedir login, faça o login de novo.
3. O site no Netlify ainda está conectado ao repositório certo? (em Site configuration → Build & deploy)

---

## 6. Receber o boletim por e-mail (opcional)

O script pode te mandar por e-mail, todo dia, um resumo só com as notícias de impacto **alto** e **médio**. Para ativar:

1. Descubra os dados de SMTP do seu provedor de e-mail (Gmail, Outlook, etc. — geralmente é preciso criar uma "senha de aplicativo", não a senha normal da conta).
2. Antes de rodar o script, configure 5 informações no computador (no Windows, isso é feito com o comando `set`; no Mac/Linux, com `export`):
   ```
   set RADAR_SMTP_HOST=smtp.gmail.com
   set RADAR_SMTP_PORT=587
   set RADAR_SMTP_USER=seuemail@gmail.com
   set RADAR_SMTP_SENHA=sua-senha-de-aplicativo
   set RADAR_EMAIL_DESTINO=fiscal@contdias.com
   ```
3. Rode o script normalmente. Se quiser rodar **sem** enviar e-mail, use:
   ```
   python radar_fiscal_scraper.py --sem-email
   ```

Se essas 5 informações não forem configuradas, o script simplesmente não tenta enviar e-mail — continua funcionando normalmente, só não manda o boletim.

---

## Personalizando o painel

Depois de já estar usando, você pode voltar aqui no Claude e pedir coisas como:

- "Adiciona um menu específico para Simples Nacional"
- "Inclui no monitoramento o site [URL]"
- "Muda as cores para [suas cores]"
- "Coloca a logo da Contdias no cabeçalho" (aí você envia a imagem da logo no chat)
- "Ajusta o texto do placar da Reforma Tributária"

---

## Sobre as fontes monitoradas

**Feeds confirmados e funcionando (RSS):** Receita Federal, Câmara dos Deputados, Conselho Federal de Contabilidade (CFC), Portal Contábeis.

**Fontes com leitura "melhor esforço" (HTML genérico, sem RSS oficial confirmado):** PGFN, Ministério da Fazenda, Senado Federal, MAPA, Jornal Contábil, e as 27 Secretarias de Fazenda estaduais (SEFAZ) — com atenção redobrada (mais notícias coletadas) em **MG, SP e RJ**, como combinado.

Sites de governo mudam de layout com alguma frequência, então de tempos em tempos alguma fonte pode parar de trazer notícias — é só avisar que eu ajusto.

---

*Prompt original desenvolvido por Nathara Muniz (Conta Mais) · Painel e script montados com Claude (Anthropic) · Setembro/2026*