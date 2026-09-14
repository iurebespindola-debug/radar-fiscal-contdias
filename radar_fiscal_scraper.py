#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radar Fiscal Contdias — coletor de notícias
=============================================

O que este script faz:
  1. Busca notícias fiscais/tributárias em fontes federais, no CFC/Contábeis
     e nas Secretarias de Fazenda (SEFAZ) dos estados.
  2. Classifica cada notícia por esfera (Federal/Estadual/Municipal),
     impacto (alto/médio/baixo) e tags (ICMS, IBS, CBS, prazo, etc.).
  3. Atualiza o arquivo radar_fiscal_contdias.html com as notícias coletadas.
  4. Opcionalmente envia um boletim por e-mail.

Como usar: veja o README.md (passo a passo sem termos técnicos).

Este script NÃO fica rodando o dia inteiro sozinho. Ele faz UMA coleta
cada vez que é executado. Para rodar todo dia às 08h, agende-o no
Agendador de Tarefas do Windows ou no cron do Mac/Linux (o README explica
como fazer isso passo a passo).
"""

import base64
import json
import os
import re
import shutil
import smtplib
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

try:
    import requests
except ImportError:
    print("Falta instalar uma biblioteca. Rode primeiro:")
    print("    pip install requests beautifulsoup4")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
    TEM_BS4 = True
except ImportError:
    TEM_BS4 = False

# =========================================================================
# CONFIGURAÇÃO — ajuste aqui conforme sua necessidade
# =========================================================================

BASE_DIR = Path(__file__).resolve().parent
HTML_PATH = BASE_DIR / "radar_fiscal_contdias.html"
JSON_DEBUG_PATH = BASE_DIR / "radar_data_ultima_coleta.json"
HISTORICO_REFORMA_PATH = BASE_DIR / "radar_historico_reforma.json"
MAX_DIAS_HISTORICO_REFORMA = 90
LOGO_PATH = BASE_DIR / "logo_contdias.png"


def _logo_base64():
    """Lê a logo da Contdias e devolve em base64, para embutir no e-mail
    (mesmo arquivo usado no painel HTML). Se o arquivo não existir, o
    e-mail sai sem logo — não trava o envio."""
    try:
        return base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    except Exception:
        return ""

TZ_BR = timezone(timedelta(hours=-3))
TIMEOUT = 15  # segundos por fonte
# Alguns sites de governo bloqueiam requisições que não parecem vir de um
# navegador comum. Usamos um User-Agent e cabeçalhos de navegador real para
# reduzir esse tipo de bloqueio (não afeta em nada o conteúdo lido).
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
HEADERS_PADRAO = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5",
}

# Quantas notícias no máximo trazer de cada fonte, para não sobrecarregar o painel
MAX_POR_FONTE = 8
MAX_POR_FONTE_ESTADO_PRIORITARIO = 10
MAX_POR_FONTE_ESTADO_COMUM = 3

# --- Fontes nacionais em formato RSS/XML (feeds confirmados em set/2026) ---
# Se uma URL parar de funcionar, o site provavelmente mudou o endereço do feed —
# basta pesquisar "<nome do site> RSS" e trocar a URL abaixo.
FONTES_RSS_FEDERAIS = [
    {
        "nome": "Receita Federal",
        "url": "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/ultimas-noticias/RSS",
        "esfera": "Federal",
    },
    {
        "nome": "Câmara dos Deputados",
        "url": "https://www.camara.leg.br/noticias/rss/ultimas-noticias",
        "esfera": "Federal",
    },
    {
        "nome": "Conselho Federal de Contabilidade (CFC)",
        "url": "https://cfc.org.br/feed/",
        "esfera": "Federal",
    },
    {
        "nome": "Portal Contábeis",
        "url": "https://www.contabeis.com.br/rss/noticias/",
        "esfera": "Federal",
    },
]

# --- Fontes nacionais adicionais pedidas, mas cujo endereço de feed não
# pôde ser confirmado no momento em que este script foi escrito (algumas
# não têm RSS público). O script tenta ler a página de notícias comum
# (HTML) com um leitor genérico — funciona bem para algumas, mal para
# outras. Se uma fonte não estiver trazendo nada, é normal: ajuste a URL
# ou peça para o Claude revisar o seletor dessa fonte específica.
FONTES_HTML_FEDERAIS = [
    {"nome": "PGFN", "url": "https://www.gov.br/pgfn/pt-br/assuntos/noticias", "esfera": "Federal"},
    {"nome": "Ministério da Fazenda", "url": "https://www.gov.br/fazenda/pt-br/assuntos/noticias", "esfera": "Federal"},
    {"nome": "Senado Federal", "url": "https://www12.senado.leg.br/noticias", "esfera": "Federal"},
    {"nome": "MAPA (Agricultura)", "url": "https://www.gov.br/agricultura/pt-br/assuntos/noticias", "esfera": "Federal"},
    {"nome": "Jornal Contábil", "url": "https://jornalcontabil.com.br/feed/", "esfera": "Federal"},
]

# --- SEFAZ dos 27 estados + DF ---
# Domínios oficiais conhecidos. Cada site tem uma estrutura diferente,
# então a coleta aqui é "melhor esforço": o script procura links de
# notícias na página informada. Para os estados prioritários (definidos
# em ESTADOS_PRIORITARIOS) ele tenta trazer mais itens.
SEFAZ_ESTADOS = {
    "AC": "https://sefaz.ac.gov.br",
    "AL": "https://www.sefaz.al.gov.br",
    "AP": "https://www.sefaz.ap.gov.br",
    "AM": "https://www.sefaz.am.gov.br",
    "BA": "https://www.sefaz.ba.gov.br",
    "CE": "https://www.sefaz.ce.gov.br",
    "DF": "https://www.fazenda.df.gov.br",
    "ES": "https://sefaz.es.gov.br",
    "GO": "https://www.economia.go.gov.br",
    "MA": "https://www.sefaz.ma.gov.br",
    "MT": "https://www.sefaz.mt.gov.br",
    "MS": "https://www.sefaz.ms.gov.br",
    "MG": "https://www.fazenda.mg.gov.br/noticias",
    "PA": "https://www.sefa.pa.gov.br",
    "PB": "https://www.sefaz.pb.gov.br",
    "PR": "https://www.fazenda.pr.gov.br",
    "PE": "https://www.sefaz.pe.gov.br",
    "PI": "https://www.sefaz.pi.gov.br",
    "RJ": "https://portal.fazenda.rj.gov.br/noticias",
    "RN": "https://set.rn.gov.br",
    "RS": "https://www.fazenda.rs.gov.br",
    "RO": "https://www.sefin.ro.gov.br",
    "RR": "https://www.sefaz.rr.gov.br",
    "SC": "https://www.sef.sc.gov.br",
    "SP": "https://portal.fazenda.sp.gov.br/noticias",
    "SE": "https://www.sefaz.se.gov.br",
    "TO": "https://www.sefaz.to.gov.br",
}
ESTADOS_PRIORITARIOS = ["MG", "SP", "RJ"]

# --- Classificação automática por palavra-chave ---
TAGS_PALAVRAS = {
    "ICMS": ["icms"],
    "ISS": ["iss ", "issqn"],
    "IBS": ["ibs"],
    "CBS": ["cbs"],
    "Imposto Seletivo": ["imposto seletivo"],
    "Reforma Tributária": ["reforma tribut"],
    "Simples Nacional": ["simples nacional"],
    "SPED": ["sped"],
    "DCTF": ["dctf"],
    "DIFAL": ["difal", "diferencial de al"],
    "FUNRURAL": ["funrural"],
    "Nota Fiscal": ["nota fiscal", "nf-e", "nfe "],
    "eSocial": ["esocial"],
    "IRPJ/CSLL": ["irpj", "csll"],
    "prazo": ["prazo", "até o dia", "vence em", "vencimento"],
    "NCM": ["ncm"],
    "CFOP": ["cfop"],
    "CST": ["cst "],
    "Parcelamento": ["parcelamento", "refis", "transação tributária", "transacao tributaria"],
    "Benefício Fiscal": ["benefício fiscal", "beneficio fiscal", "incentivo fiscal", "crédito presumido", "credito presumido", "regime especial"],
    "Alíquota": ["alíquota", "aliquota"],
}

# =========================================================================
# FILTRO DE RELEVÂNCIA — só o que é realmente tributário
# =========================================================================
# A pedido do escritório: o radar deve trazer só notícias sobre alíquota de
# imposto, alteração de declarações fiscais/obrigações acessórias, NCM,
# CFOP, CST, parcelamentos e benefícios fiscais — para todas as esferas
# (Federal, Estadual, Municipal). O que não se encaixa nisso (RH, saúde,
# eventos, notícias administrativas genéricas etc.) fica fora do radar
# inteiro, não só do e-mail.
TERMOS_RELEVANTES_TEXTO = [
    # alíquota / carga tributária
    "alíquota", "aliquota", "carga tributária", "carga tributaria",
    "aumento de imposto", "redução de imposto", "reducao de imposto",
    "majoração de imposto", "majoracao de imposto",
    # declarações fiscais / obrigações acessórias
    "declaração fiscal", "declaracao fiscal", "declaração de imposto",
    "declaracao de imposto", "obrigação acessória", "obrigacao acessoria",
    "escrituração fiscal", "escrituracao fiscal", "dctf",
    "dirf", "esocial", "nota fiscal", "nf-e", "nfe ",
    "nfc-e",
    # parcelamentos
    "parcelamento", "parcelar débito", "parcelar debito", "refis",
    "transação tributária", "transacao tributaria", "regularização fiscal",
    "regularizacao fiscal", "anistia fiscal", "reparcelamento",
    # benefícios fiscais
    "benefício fiscal", "beneficio fiscal", "incentivo fiscal",
    "crédito presumido", "credito presumido", "regime especial",
    "redução de base de cálculo", "reducao de base de calculo",
    "diferimento do icms", "isenção fiscal", "isencao fiscal",
    "isenção de imposto", "isencao de imposto",
    # tributos e temas nomeados (a notícia já nasce tributária)
    "icms", "iss ", "issqn", "ibs", "cbs", "imposto seletivo", "difal",
    "irpj", "csll", "funrural", "simples nacional", "reforma tributária",
    "reforma tributaria", "iptu", "itbi",
    # vocabulário tributário mais amplo — os itens acima são exemplos, não
    # uma lista fechada; estes termos cobrem o resto do universo fiscal
    # (arrecadação, fiscalização, regimes de apuração, fraude fiscal etc.)
    "imposto", "tribut",  # "tribut" cobre tributo/tributário/tributação
    "fisco", "arrecadação", "arrecadacao", "sonegação", "sonegacao",
    "lucro real", "lucro presumido", "guerra fiscal", "malha fiscal",
    "auto de infração", "auto de infracao", "confaz", "irpf",
    "imposto de renda", "planejamento tributário", "planejamento tributario",
    "elisão fiscal", "elisao fiscal", "bitributação", "bitributacao",
    "restituição de imposto", "restituicao de imposto", "fraude fiscal",
    "sped fiscal", "domicílio tributário", "domicilio tributario",
]
# Termos curtos/ambíguos — exigem borda de palavra para não pegar como
# substring de outra palavra qualquer (ex.: "pis" dentro de outro termo).
TERMOS_RELEVANTES_REGEX = re.compile(
    r"\b(ncm|cfop|cst|csosn|pis|cofins|ipi|gia|ecf|ecd|efd|sped|mei)\b", re.IGNORECASE
)

# Textos de navegação/institucionais que aparecem em qualquer site de
# governo (menus, botões, rodapé) e que o coletor "leitura genérica" às
# vezes confunde com notícia de verdade. Isso é filtrado mesmo que a
# notícia bata com um termo tributário — não é sobre o assunto, é lixo de
# interface.
PADROES_NAO_NOTICIA = re.compile(
    r"agilize seu atendimento|confira a autenticidade|acesse aqui|clique aqui|"
    r"saiba mais aqui|fale conosco|canais? de atendimento|central de atendimento|"
    r"perguntas frequentes|dúvidas frequentes|duvidas frequentes|sobre n[oó]s|"
    r"quem somos|mapa do site|política de privacidade|politica de privacidade|"
    r"acessibilidade|fa[cç]a login|agende seu atendimento|conselho superior|"
    r"corregedoria|tribunal administrativo|ouvidoria|organograma|"
    r"estrutura organizacional|estrutura administrativa|^conselho de contribuintes$",
    re.IGNORECASE,
)

# Tipos de conteúdo que não interessam mesmo falando de um tema tributário
# (curso, concurso público, evento etc.) — a pedido do escritório.
PADROES_INDESEJADOS = re.compile(
    r"\bcursos?\b|capacita[çc][ãa]o|\bwebinar\b|\btreinamento\b|\bpalestra\b|"
    r"concurso p[uú]blico|\bcertame\b|processo seletivo|vagas para|"
    r"edital de concurso|inscri[çc][õo]es abertas",
    re.IGNORECASE,
)

# Conectores que não contam como "palavra de conteúdo" ao avaliar se um
# título parece nome de página/menu (ex.: "Documentos de Arrecadação").
_CONECTORES = {
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas", "para",
    "com", "sobre", "e", "a", "o", "as", "os", "um", "uma", "ao", "à", "às",
}


def _parece_pagina_institucional(titulo, resumo):
    """
    Sem RSS, o coletor 'leitura genérica' das SEFAZ pega qualquer link
    grande como se fosse notícia — inclusive nomes de seção/serviço do site
    (ex.: "Procedimentos Tributários", "Domicílio Tributário Eletrônico").
    Esses não têm resumo real (só o texto do link) e, diferente de uma
    manchete, costumam ser uma frase curta com quase toda palavra
    maiúscula. Notícia de verdade tem verbo/frase e normalmente vem com
    resumo (RSS) ou é mais longa.
    """
    if resumo:
        return False
    palavras = titulo.strip().split()
    if len(palavras) > 6:
        return False
    conteudo = [p for p in palavras[1:] if p.lower() not in _CONECTORES]
    if not conteudo:
        return False
    maiusculas = sum(1 for p in conteudo if p[:1].isupper())
    return (maiusculas / len(conteudo)) >= 0.8


def eh_relevante_tributario(titulo, resumo):
    texto = f"{titulo} {resumo or ''}".lower()
    if PADROES_NAO_NOTICIA.search(texto) or PADROES_INDESEJADOS.search(texto):
        return False
    if _parece_pagina_institucional(titulo, resumo):
        return False
    if any(t in texto for t in TERMOS_RELEVANTES_TEXTO):
        return True
    return bool(TERMOS_RELEVANTES_REGEX.search(texto))

PALAVRAS_ALTO_IMPACTO = [
    "obrigatori", "obrigat", "multa", "penalidade", "aumento de al",
    "nova lei", "sancionada", "publicada", "entra em vigor", "prazo final",
    "prazo se encerra", "mudança", "alteração", "revoga", "decisão do stf",
    "decisão do supremo", "aprovad", "vence em", "vencimento",
]
PALAVRAS_BAIXO_IMPACTO = [
    "curso", "evento", "podcast", "live", "webinar", "entrevista",
    "opinião", "artigo", "aniversário", "homenagem",
]

# =========================================================================
# COLETA — RSS/XML
# =========================================================================

# Preenchida a cada coleta com (nome_fonte, sucesso, motivo_erro) — usada
# para detectar fontes quebradas há vários dias seguidos (ver
# atualizar_saude_fontes mais abaixo).
_RESULTADOS_FONTES = []


def _tag_local(tag):
    """Remove o namespace de uma tag do ElementTree, ex: '{ns}item' -> 'item'."""
    return tag.split("}")[-1] if "}" in tag else tag


def buscar_url(url):
    resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS_PADRAO)
    resp.raise_for_status()
    return resp


def parse_rss(conteudo_bytes):
    """Lê RSS 2.0, RSS 1.0/RDF e Atom (com ou sem namespace), devolvendo
    lista de dicts {titulo, resumo, url, data}."""
    itens = []
    root = ET.fromstring(conteudo_bytes)

    # RSS 2.0 e RSS 1.0/RDF usam <item>; Atom usa <entry> — ignoramos o
    # namespace (muitos feeds de governo usam RDF com xmlns padrão, o que
    # faz "item" virar "{namespace}item").
    encontrados = [el for el in root.iter() if _tag_local(el.tag) in ("item", "entry")]

    for it in encontrados:
        titulo = _texto(it, "title")
        resumo = _texto(it, "description") or _texto(it, "summary") or _texto(it, "content")
        link = _link(it)
        data_raw = (
            _texto(it, "pubDate")
            or _texto(it, "date")
            or _texto(it, "published")
            or _texto(it, "updated")
        )
        data_iso = _normaliza_data(data_raw)
        if titulo:
            itens.append({
                "titulo": _limpa_html(titulo),
                "resumo": _limpa_html(resumo)[:280] if resumo else "",
                "url": link or "",
                "data": data_iso,
            })
    return itens


def _texto(elemento, tag_alvo):
    for child in elemento:
        if _tag_local(child.tag) == tag_alvo and child.text:
            return child.text.strip()
    return ""


def _link(elemento):
    for child in elemento:
        if _tag_local(child.tag) == "link":
            if child.text and child.text.strip():
                return child.text.strip()
            href = child.get("href")
            if href:
                return href
    return ""


def _limpa_html(txt):
    if not txt:
        return ""
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()


def _normaliza_data(data_raw):
    if not data_raw:
        return datetime.now(TZ_BR).strftime("%Y-%m-%d")
    formatos = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ]
    for fmt in formatos:
        try:
            return datetime.strptime(data_raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # último recurso: pega os 10 primeiros caracteres em formato de data se houver
    m = re.search(r"\d{4}-\d{2}-\d{2}", data_raw)
    if m:
        return m.group(0)
    return datetime.now(TZ_BR).strftime("%Y-%m-%d")


def coletar_fonte_rss(fonte, limite):
    try:
        resp = buscar_url(fonte["url"])
        itens = parse_rss(resp.content)[:limite]
        resultado = []
        for it in itens:
            resultado.append(monta_item(it["titulo"], it["resumo"], fonte["esfera"], fonte["nome"], it["url"], it["data"]))
        print(f"  [ok] {fonte['nome']}: {len(resultado)} item(ns)")
        _RESULTADOS_FONTES.append((fonte["nome"], True, ""))
        return resultado
    except Exception as e:
        print(f"  [falhou] {fonte['nome']}: {e}")
        _RESULTADOS_FONTES.append((fonte["nome"], False, str(e)))
        return []


# =========================================================================
# COLETA — HTML genérico (fallback para fontes sem RSS conhecido)
# =========================================================================

def coletar_fonte_html(fonte, limite, esfera=None, estado=None):
    if not TEM_BS4:
        print(f"  [pulado] {fonte['nome']}: instale beautifulsoup4 para coletar fontes sem RSS")
        return []
    try:
        resp = buscar_url(fonte["url"])
        soup = BeautifulSoup(resp.content, "html.parser")
        candidatos = []
        # Estratégia simples e tolerante: pega links de texto razoavelmente
        # longo (títulos de notícia costumam ter mais de 25 caracteres).
        for a in soup.find_all("a", href=True):
            texto = a.get_text(strip=True)
            # Alguns sites colam a data antes do título sem espaço
            # (ex.: "01/12/25Governo do Estado divulga..."); separa isso.
            texto = re.sub(r"^(\d{1,2}/\d{1,2}/\d{2,4})(?=[A-ZÀ-Ú])", r"\1 ", texto)
            if texto and 25 <= len(texto) <= 200:
                href = a["href"]
                if href.startswith("/"):
                    base = re.match(r"https?://[^/]+", fonte["url"])
                    href = (base.group(0) if base else "") + href
                candidatos.append((texto, href))

        vistos = set()
        resultado = []
        for texto, href in candidatos:
            if texto in vistos:
                continue
            vistos.add(texto)
            nome_fonte = fonte["nome"] if not estado else f"SEFAZ-{estado}"
            resultado.append(monta_item(texto, "", esfera or fonte["esfera"], nome_fonte, href, datetime.now(TZ_BR).strftime("%Y-%m-%d")))
            if len(resultado) >= limite:
                break
        print(f"  [ok] {fonte['nome']}: {len(resultado)} item(ns) (leitura genérica)")
        _RESULTADOS_FONTES.append((fonte["nome"] if not estado else f"SEFAZ-{estado}", True, ""))
        return resultado
    except Exception as e:
        print(f"  [falhou] {fonte['nome']}: {e}")
        _RESULTADOS_FONTES.append((fonte["nome"] if not estado else f"SEFAZ-{estado}", False, str(e)))
        return []


# =========================================================================
# CLASSIFICAÇÃO
# =========================================================================

def classifica_tags(titulo, resumo):
    texto = (titulo + " " + resumo).lower()
    tags = []
    for tag, palavras in TAGS_PALAVRAS.items():
        if any(p in texto for p in palavras):
            tags.append(tag)
    return tags


def classifica_impacto(titulo, resumo, tags):
    texto = (titulo + " " + resumo).lower()
    if any(p in texto for p in PALAVRAS_ALTO_IMPACTO):
        return "alto"
    if any(p in texto for p in PALAVRAS_BAIXO_IMPACTO):
        return "baixo"
    # notícias sobre a Reforma Tributária ou obrigações específicas tendem
    # a ser pelo menos de impacto médio
    if tags:
        return "medio"
    return "baixo"


def monta_item(titulo, resumo, esfera, fonte, url, data):
    tags = classifica_tags(titulo, resumo)
    impacto = classifica_impacto(titulo, resumo, tags)
    item_id = re.sub(r"[^a-z0-9]+", "-", titulo.lower())[:60] + "-" + re.sub(r"\W", "", (url or fonte))[-8:]
    return {
        "id": item_id,
        "titulo": titulo,
        "resumo": resumo or "",
        "esfera": esfera,
        "impacto": impacto,
        "data": data,
        "fonte": fonte,
        "url": url or "#",
        "tags": tags,
    }


# =========================================================================
# COLETA GERAL
# =========================================================================

def coleta_completa():
    todos_itens = []
    _RESULTADOS_FONTES.clear()

    print("Coletando fontes federais (RSS)...")
    for fonte in FONTES_RSS_FEDERAIS:
        todos_itens.extend(coletar_fonte_rss(fonte, MAX_POR_FONTE))

    print("Coletando fontes federais adicionais (HTML)...")
    for fonte in FONTES_HTML_FEDERAIS:
        # Jornal Contábil está configurado como feed; as demais são HTML genérico
        if fonte["url"].endswith("/feed/"):
            todos_itens.extend(coletar_fonte_rss(fonte, MAX_POR_FONTE))
        else:
            todos_itens.extend(coletar_fonte_html(fonte, MAX_POR_FONTE))

    print("Coletando SEFAZ dos estados (prioridade: %s)..." % ", ".join(ESTADOS_PRIORITARIOS))
    for uf, url in SEFAZ_ESTADOS.items():
        limite = MAX_POR_FONTE_ESTADO_PRIORITARIO if uf in ESTADOS_PRIORITARIOS else MAX_POR_FONTE_ESTADO_COMUM
        fonte = {"nome": f"SEFAZ-{uf}", "url": url, "esfera": "Estadual"}
        todos_itens.extend(coletar_fonte_html(fonte, limite, esfera="Estadual", estado=uf))

    # remove duplicados por título
    vistos = set()
    itens_unicos = []
    for item in todos_itens:
        chave = item["titulo"].strip().lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        itens_unicos.append(item)

    antes = len(itens_unicos)
    itens_unicos = [i for i in itens_unicos if eh_relevante_tributario(i["titulo"], i["resumo"])]
    print(f"Filtro de relevância tributária: {antes} -> {len(itens_unicos)} notícia(s).")

    return itens_unicos


# =========================================================================
# SAÚDE DAS FONTES — detecta fonte quebrada há vários dias seguidos
# =========================================================================
# Uma fonte falhar uma vez é normal (instabilidade momentânea do site).
# O que interessa avisar é quando ela para de funcionar por vários dias
# seguidos — sinal de que o endereço mudou de verdade e precisa de ajuste
# manual. Guardamos o histórico num arquivo simples e só alertamos a
# partir de LIMIAR_ALERTA_SAUDE falhas consecutivas.
SAUDE_FONTES_PATH = BASE_DIR / "radar_saude_fontes.json"
LIMIAR_ALERTA_SAUDE = 3


def atualizar_saude_fontes():
    """
    Usa o que foi registrado em _RESULTADOS_FONTES durante a coleta para
    atualizar o histórico de saúde de cada fonte, e devolve a lista das
    que estão quebradas há LIMIAR_ALERTA_SAUDE dias ou mais.
    """
    try:
        estado = json.loads(SAUDE_FONTES_PATH.read_text(encoding="utf-8"))
    except Exception:
        estado = {}

    hoje = datetime.now(TZ_BR).strftime("%Y-%m-%d")
    # Se uma fonte aparecer mais de uma vez na mesma coleta (não deveria,
    # mas por segurança), considera sucesso se pelo menos uma tentativa deu certo.
    por_fonte = {}
    for nome, sucesso, motivo in _RESULTADOS_FONTES:
        if nome not in por_fonte or sucesso:
            por_fonte[nome] = (sucesso, motivo)

    for nome, (sucesso, motivo) in por_fonte.items():
        registro = estado.get(nome, {"falhas_seguidas": 0})
        if sucesso:
            registro["falhas_seguidas"] = 0
            registro.pop("motivo", None)
        else:
            registro["falhas_seguidas"] = registro.get("falhas_seguidas", 0) + 1
            registro["motivo"] = motivo
        registro["ultima_atualizacao"] = hoje
        estado[nome] = registro

    SAUDE_FONTES_PATH.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")

    quebradas = [
        {"fonte": nome, "dias": r["falhas_seguidas"], "motivo": r.get("motivo", "")}
        for nome, r in estado.items()
        if r.get("falhas_seguidas", 0) >= LIMIAR_ALERTA_SAUDE
    ]
    quebradas.sort(key=lambda x: -x["dias"])
    return quebradas


def placar_reforma_tributaria():
    """
    Placar editorial de progresso da Reforma Tributária.
    Ajuste manualmente os valores de 'progresso' (0-100) conforme o
    andamento real — não há uma API oficial única que consolide isso.
    """
    return [
        {"nome": "IBS", "fase": "Regulamentação infralegal", "progresso": 42,
         "nota": "Leis complementares publicadas; decretos e portarias em elaboração."},
        {"nome": "CBS", "fase": "Regulamentação infralegal", "progresso": 45,
         "nota": "Comitê gestor em fase de testes; alíquotas por setor em definição."},
        {"nome": "Imposto Seletivo", "fase": "Definição de incidência", "progresso": 30,
         "nota": "Lista de produtos/serviços sujeitos ainda em debate."},
    ]


# =========================================================================
# HISTÓRICO DA REFORMA TRIBUTÁRIA
# =========================================================================
# Guarda, a cada coleta do dia, uma foto do placar de progresso e das
# manchetes relacionadas à Reforma Tributária — separadas em "Simples
# Nacional" e "demais mudanças" (IBS/CBS/Imposto Seletivo). É o que permite
# mostrar uma evolução de verdade ao longo do tempo na aba Reforma
# Tributária, em vez de só a foto do dia.

def _carregar_historico_reforma():
    if HISTORICO_REFORMA_PATH.exists():
        try:
            return json.loads(HISTORICO_REFORMA_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def atualizar_historico_reforma(itens, placar):
    historico = _carregar_historico_reforma()
    hoje = datetime.now(TZ_BR).strftime("%Y-%m-%d")

    def _tem_tag(item, tag):
        return tag in (item.get("tags") or [])

    reforma_itens = [
        i for i in itens
        if any(_tem_tag(i, t) for t in ("IBS", "CBS", "Imposto Seletivo", "Reforma Tributária", "Simples Nacional"))
    ]
    simples = [i for i in reforma_itens if _tem_tag(i, "Simples Nacional")]
    demais = [i for i in reforma_itens if not _tem_tag(i, "Simples Nacional")]

    def _resumido(i):
        return {"titulo": i["titulo"], "url": i["url"], "fonte": i["fonte"], "impacto": i["impacto"]}

    entrada = {
        "data": hoje,
        "placar": [{"nome": p["nome"], "progresso": p["progresso"]} for p in placar],
        "simples_nacional": [_resumido(i) for i in simples],
        "demais_mudancas": [_resumido(i) for i in demais],
    }

    # Se já rodou hoje antes, substitui a entrada de hoje em vez de duplicar
    historico = [h for h in historico if h["data"] != hoje]
    historico.append(entrada)
    historico.sort(key=lambda h: h["data"])
    historico = historico[-MAX_DIAS_HISTORICO_REFORMA:]

    HISTORICO_REFORMA_PATH.write_text(json.dumps(historico, ensure_ascii=False, indent=2), encoding="utf-8")
    return historico


# =========================================================================
# ATUALIZAÇÃO DO HTML
# =========================================================================

PADRAO_BLOCO = re.compile(
    r'(<script id="radar-data" type="application/json">\s*\n)(.*?)(\n\s*</script>)',
    re.DOTALL,
)


def atualizar_html(itens, caminho_html=HTML_PATH):
    if not caminho_html.exists():
        print(f"[ERRO] Não encontrei {caminho_html}. Coloque este script na mesma pasta do radar_fiscal_contdias.html.")
        return False

    placar = placar_reforma_tributaria()
    historico_reforma = atualizar_historico_reforma(itens, placar)

    dados = {
        "gerado_em": datetime.now(TZ_BR).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "exemplo": False,
        "reforma_tributaria": placar,
        "historico_reforma": historico_reforma,
        "itens": itens,
    }

    # formata o offset -0300 como -03:00 (ISO correto)
    dados["gerado_em"] = dados["gerado_em"][:-2] + ":" + dados["gerado_em"][-2:]

    json_texto = json.dumps(dados, ensure_ascii=False, indent=2)
    # Proteção extra: se algum título/resumo coletado contiver literalmente
    # "</script>", isso quebraria a página. Escapamos essa sequência.
    json_texto = json_texto.replace("</script", "<\\/script")

    html_original = caminho_html.read_text(encoding="utf-8")
    novo_html, n = PADRAO_BLOCO.subn(lambda m: m.group(1) + json_texto + m.group(3), html_original)

    if n == 0:
        print("[ERRO] Não encontrei o bloco de dados no HTML (marcador radar-data). "
              "Não mexi no arquivo para não estragar nada.")
        return False

    caminho_html.write_text(novo_html, encoding="utf-8")
    JSON_DEBUG_PATH.write_text(json_texto, encoding="utf-8")
    print(f"[ok] {caminho_html.name} atualizado com {len(itens)} notícia(s).")
    return True


# =========================================================================
# PUBLICAÇÃO AUTOMÁTICA (GitHub -> Netlify)
# =========================================================================
# Depois de atualizar o HTML local, copia para index.html e manda pro
# GitHub. O Netlify está configurado para publicar sozinho a cada push
# nesse repositório — então isso é o que faz o link do painel (o mesmo
# link sempre) refletir a coleta mais recente, sem intervenção manual.
# Se o git não estiver configurado (sem repositório, sem remoto, sem
# login salvo), só avisa e segue em frente — não trava o resto do script.

INDEX_PATH = BASE_DIR / "index.html"


def _git_exe():
    encontrado = shutil.which("git")
    if encontrado:
        return encontrado
    for candidato in (
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files\Git\bin\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
    ):
        if Path(candidato).exists():
            return candidato
    return None


def publicar_no_github():
    git = _git_exe()
    if not git:
        print("[publicacao] git não encontrado — pulando publicação online.")
        return

    try:
        shutil.copyfile(HTML_PATH, INDEX_PATH)

        def rodar(*args):
            return subprocess.run(
                [git, *args], cwd=BASE_DIR, capture_output=True, text=True, timeout=60
            )

        rodar("add", "index.html")
        commit = rodar("commit", "-m", f"Atualizacao automatica {datetime.now(TZ_BR).strftime('%Y-%m-%d %H:%M')}")
        saida_commit = (commit.stdout + commit.stderr).lower()
        sem_mudanca = "nothing to commit" in saida_commit or "no changes added to commit" in saida_commit
        if commit.returncode != 0 and not sem_mudanca:
            print(f"[publicacao] Falha ao commitar: {commit.stderr.strip()}")
            return
        if sem_mudanca:
            print("[publicacao] Painel sem mudanças desde a última publicação — nada a enviar.")
            return

        push = rodar("push", "origin", "main")
        if push.returncode != 0:
            print(f"[publicacao] Falha ao publicar no GitHub: {push.stderr.strip()}")
            return

        print("[publicacao] Painel publicado no GitHub — o Netlify vai atualizar o link em instantes.")
    except Exception as e:
        print(f"[publicacao] Erro inesperado ao publicar: {e}")


# =========================================================================
# BOLETIM POR E-MAIL (opcional)
# =========================================================================

ORDEM_ESFERA = ["Federal", "Estadual", "Municipal", "Internacional"]
ICONE_ESFERA = {"Federal": "&#127963;", "Estadual": "&#128506;", "Municipal": "&#127961;", "Internacional": "&#127760;"}
COR_IMPACTO = {"alto": "#B3261E", "medio": "#9A6B12", "baixo": "#5B6470"}
BG_IMPACTO = {"alto": "#FBEAE9", "medio": "#FBF1DD", "baixo": "#EEF0F2"}

# Máximo de notícias de impacto médio por esfera no e-mail (impacto alto nunca
# é cortado). É só uma trava de segurança para um dia com volume anormal —
# no dia a dia normal, o filtro por impacto já deixa a lista curta sozinho.
MAX_MEDIO_POR_ESFERA_EMAIL = 10

# Fontes de notícias gerais (cobrem todo tipo de pauta — agricultura,
# trânsito, saúde etc. — não só tributária). Para essas, só confiamos na
# classificação de impacto alto/médio se a notícia também bateu com alguma
# tag fiscal de verdade (ICMS, prazo, Simples Nacional...). Fontes
# especializadas em tributos/contabilidade (Receita Federal, PGFN, SEFAZ,
# CFC, Contábeis etc.) não precisam desse filtro extra — o próprio tema da
# fonte já garante que é relevante.
FONTES_GENERICAS = {"Câmara dos Deputados", "Senado Federal", "MAPA (Agricultura)"}


def selecionar_curadoria(itens):
    """
    Escolhe o que realmente vale a pena mandar por e-mail: só impacto ALTO
    (sempre, sem corte) e MÉDIO (até MAX_MEDIO_POR_ESFERA_EMAIL por esfera),
    descartando falsos positivos de fontes genéricas sem tag fiscal.
    Impacto BAIXO fica de fora do boletim — mas continua no painel completo.
    """
    relevante = lambda i: i["fonte"] not in FONTES_GENERICAS or bool(i.get("tags"))

    alto = [i for i in itens if i["impacto"] == "alto" and relevante(i)]
    medio = [i for i in itens if i["impacto"] == "medio" and relevante(i)]

    medio_cortado = []
    for esfera in ORDEM_ESFERA:
        do_grupo = [i for i in medio if i["esfera"] == esfera]
        medio_cortado.extend(do_grupo[:MAX_MEDIO_POR_ESFERA_EMAIL])

    curados = alto + medio_cortado
    curados.sort(key=lambda i: (
        ORDEM_ESFERA.index(i["esfera"]) if i["esfera"] in ORDEM_ESFERA else len(ORDEM_ESFERA),
        0 if i["impacto"] == "alto" else 1,
    ))
    return curados, len(itens) - len(curados)


def _card_html(i):
    cor = COR_IMPACTO.get(i["impacto"], "#5B6470")
    bg = BG_IMPACTO.get(i["impacto"], "#EEF0F2")
    tags = "".join(
        f'<span style="font-size:10.5px;background:#F0F2F4;color:#3D444C;padding:3px 8px;'
        f'border-radius:6px;margin:0 5px 5px 0;display:inline-block">{t}</span>'
        for t in i.get("tags", [])
    )
    destaque = i["impacto"] == "alto"
    tam_titulo = "16px" if destaque else "14px"
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px">
<tr>
<td width="5" style="background:{cor};border-radius:4px 0 0 4px"></td>
<td style="background:#fff;border:1px solid #E1E5E9;border-left:none;border-radius:0 8px 8px 0;padding:14px 16px">
<span style="font-size:10.5px;font-weight:700;color:{cor};background:{bg};padding:3px 9px;
border-radius:999px;text-transform:uppercase;letter-spacing:.4px">{'&#128680; ' if destaque else ''}{i['impacto']}</span>
<div style="margin-top:9px">
<a href="{i['url']}" style="color:#123524;font-weight:700;font-size:{tam_titulo};line-height:1.4;text-decoration:none">{i['titulo']}</a>
</div>
<div style="font-size:11.5px;color:#8B94A0;margin-top:6px">{i['fonte']} &middot; {i['data']}</div>
{f'<div style="margin-top:8px">{tags}</div>' if tags else ''}
<div style="margin-top:10px">
<a href="{i['url']}" style="display:inline-block;background:#1B4A32;color:#fff;font-size:12px;font-weight:600;
text-decoration:none;padding:7px 14px;border-radius:7px">Ler noticia completa &rarr;</a>
</div>
</td>
</tr>
</table>"""


def _monta_alerta_fontes_html(fontes_quebradas):
    if not fontes_quebradas:
        return ""
    linhas = "".join(
        f'<div style="padding:3px 0">&bull; <b>{f["fonte"]}</b> — sem coletar há {f["dias"]} dia(s)</div>'
        for f in fontes_quebradas
    )
    return f"""
<tr><td style="padding:14px 22px 0">
<div style="background:#FBEAE9;border:1px solid #F3C6C3;border-radius:8px;padding:12px 16px;font-size:12.5px;color:#8A2A22">
<b>&#9888; Atenção técnica:</b> {len(fontes_quebradas)} fonte(s) parecem ter mudado de endereço ou estrutura e não
estão sendo coletadas há alguns dias — provavelmente precisam de ajuste manual no script.
{linhas}
</div>
</td></tr>"""


def _monta_html_boletim(itens_curados, total_coletado, restante, data_str, fontes_quebradas=None):
    n_alto = sum(1 for i in itens_curados if i["impacto"] == "alto")
    n_medio = sum(1 for i in itens_curados if i["impacto"] == "medio")

    pills = f"""
<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:14px"><tr>
<td style="background:#B3261E;color:#fff;font-size:12px;font-weight:700;padding:7px 14px;border-radius:999px;margin-right:8px">
&#128680; {n_alto} DE ALTO IMPACTO</td>
<td width="8"></td>
<td style="background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.3);color:#fff;font-size:12px;font-weight:700;padding:7px 14px;border-radius:999px">
&#9888; {n_medio} DE MEDIO IMPACTO</td>
</tr></table>""" if (n_alto or n_medio) else ""

    secoes = []
    if not itens_curados:
        secoes.append(
            '<tr><td style="padding:28px 4px;text-align:center;color:#5B6470;font-size:13.5px">'
            'Nenhuma noticia de impacto alto ou medio hoje. Dia tranquilo — '
            f'as {total_coletado} noticias de rotina coletadas estao no painel completo.</td></tr>'
        )
    else:
        for esfera in ORDEM_ESFERA:
            do_grupo = [i for i in itens_curados if i["esfera"] == esfera]
            if not do_grupo:
                continue
            cards = "".join(_card_html(i) for i in do_grupo)
            secoes.append(
                '<tr><td style="padding:24px 0 10px">'
                f'<span style="font-size:13px;font-weight:700;color:#123524;text-transform:uppercase;letter-spacing:.5px">'
                f'{ICONE_ESFERA.get(esfera, "")} {esfera}</span> '
                f'<span style="font-size:12px;color:#8B94A0">&middot; {len(do_grupo)} noticia(s)</span>'
                f'</td></tr><tr><td>{cards}</td></tr>'
            )

    rodape_extra = (
        f'<div style="margin-top:6px">Mais {restante} noticia(s) de rotina foram coletadas hoje '
        'e estao disponiveis no painel completo, mas nao entraram neste resumo.</div>'
        if restante > 0 else ""
    )

    logo_b64 = _logo_base64()
    logo_html = (
        '<tr><td style="padding:0 0 14px">'
        '<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
        '<td style="background:#fff;border-radius:8px;padding:8px 12px">'
        f'<img src="data:image/png;base64,{logo_b64}" alt="Contdias" height="24" '
        'style="display:block;height:24px;width:auto"></td>'
        '</tr></table></td></tr>'
        if logo_b64 else ""
    )

    return f"""\
<html><body style="margin:0;background:#F8F9FA;font-family:-apple-system,Segoe UI,Arial,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%">
<tr><td style="background:#123524;border-radius:10px 10px 0 0;padding:22px 26px 20px">
<table role="presentation" cellpadding="0" cellspacing="0">{logo_html}</table>
<div style="color:#fff;font-size:24px;font-weight:800;letter-spacing:.2px">&#9888; Fique de olho</div>
<div style="color:#CFE3D7;font-size:12.5px;margin-top:4px">Contdias Contabilidade &middot; Departamento Fiscal &middot; {data_str}</div>
{pills}
</td></tr>
{_monta_alerta_fontes_html(fontes_quebradas)}
<tr><td style="background:#E0A73E;height:5px;line-height:5px;font-size:0">&nbsp;</td></tr>
<tr><td style="background:#fff;border:1px solid #E1E5E9;border-top:none;border-radius:0 0 10px 10px;padding:4px 22px 22px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(secoes)}</table>
</td></tr>
<tr><td style="padding:16px 10px;text-align:center;color:#8B94A0;font-size:11px">
Boletim automatico diario &mdash; Fique de olho, Contdias<br>{rodape_extra}
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""


def enviar_boletim_email(itens, fontes_quebradas=None):
    """
    Envia por e-mail, todo dia, só o que é impacto ALTO ou MÉDIO (a curadoria
    do que realmente importa — veja selecionar_curadoria()). Impacto BAIXO
    fica de fora do e-mail, mas continua no painel completo. Só funciona se
    as variáveis de ambiente abaixo estiverem configuradas (veja o README):
      RADAR_SMTP_HOST, RADAR_SMTP_PORT, RADAR_SMTP_USER, RADAR_SMTP_SENHA,
      RADAR_EMAIL_DESTINO

    fontes_quebradas: lista opcional (de atualizar_saude_fontes()) de fontes
    que estão falhando há vários dias seguidos — vira um aviso no topo do
    e-mail para alguém dar uma olhada no script.
    """
    host = os.environ.get("RADAR_SMTP_HOST")
    porta = os.environ.get("RADAR_SMTP_PORT")
    usuario = os.environ.get("RADAR_SMTP_USER")
    senha = os.environ.get("RADAR_SMTP_SENHA")
    destino_raw = os.environ.get("RADAR_EMAIL_DESTINO")

    if not all([host, porta, usuario, senha, destino_raw]):
        print("[boletim] Envio de e-mail não configurado (variáveis de ambiente ausentes) — pulando.")
        return

    # Aceita um ou vários e-mails separados por vírgula em RADAR_EMAIL_DESTINO
    destinatarios = [e.strip() for e in destino_raw.split(",") if e.strip()]
    destino = ", ".join(destinatarios)

    curados, restante = selecionar_curadoria(itens)
    data_str = datetime.now(TZ_BR).strftime("%d/%m/%Y")
    html = _monta_html_boletim(curados, len(itens), restante, data_str, fontes_quebradas)

    linhas_txt = [
        f"Fique de olho ⚠ — Boletim de {data_str}",
        f"{len(curados)} notícia(s) de impacto alto/médio hoje "
        f"(+{restante} de rotina no painel completo)." if curados else "Nenhuma notícia de impacto alto/médio hoje.",
        "",
    ]
    for i in curados:
        linhas_txt.append(f"[{i['impacto'].upper()}] {i['esfera']} — {i['titulo']} ({i['fonte']}, {i['data']})")
        linhas_txt.append(f"  {i['url']}")
    texto = "\n".join(linhas_txt)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Fique de olho ⚠ — {data_str} ({len(curados)} {'alerta' if len(curados) == 1 else 'alertas'})"
    msg["From"] = usuario
    msg["To"] = destino
    msg.attach(MIMEText(texto, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(host, int(porta), timeout=TIMEOUT) as servidor:
            servidor.starttls()
            servidor.login(usuario, senha)
            servidor.sendmail(usuario, destinatarios, msg.as_string())
        print(f"[boletim] E-mail enviado para {destino}.")
    except Exception as e:
        print(f"[boletim] Falha ao enviar e-mail: {e}")


# =========================================================================
# EXECUÇÃO
# =========================================================================

def main():
    enviar_email = "--sem-email" not in sys.argv
    publicar_online = "--sem-publicar" not in sys.argv

    print("=" * 60)
    print("Radar Fiscal Contdias — iniciando coleta em", datetime.now(TZ_BR).strftime("%d/%m/%Y %H:%M"))
    print("=" * 60)

    try:
        itens = coleta_completa()
    except Exception:
        print("[ERRO GERAL] A coleta falhou inesperadamente:")
        traceback.print_exc()
        sys.exit(1)

    print(f"\nTotal de notícias únicas coletadas: {len(itens)}")

    fontes_quebradas = atualizar_saude_fontes()
    if fontes_quebradas:
        print(f"\n[saude] {len(fontes_quebradas)} fonte(s) falhando há {LIMIAR_ALERTA_SAUDE}+ dias seguidos:")
        for f in fontes_quebradas:
            print(f"  - {f['fonte']}: {f['dias']} dia(s) — {f['motivo']}")

    ok = atualizar_html(itens)

    if ok and publicar_online:
        publicar_no_github()

    if enviar_email:
        enviar_boletim_email(itens, fontes_quebradas)

    if ok:
        print("\nConcluído. Abra o radar_fiscal_contdias.html no navegador para ver o resultado.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
