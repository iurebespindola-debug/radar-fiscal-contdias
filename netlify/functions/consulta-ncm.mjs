// Função serverless do Netlify (roda no servidor deles, não no navegador de
// quem acessa) — existe porque buscadorncm.com.br não permite chamada direta
// do navegador (bloqueio de CORS). Ela busca a página pública do NCM,
// extrai os dados estruturados (JSON-LD) que o próprio site já publica pra
// SEO, e devolve só o que interessa (cClassTrib, CST, resumo) em JSON limpo.
//
// Fonte: https://buscadorncm.com.br (agregador especializado em NCM/Reforma
// Tributária, não é fonte oficial do governo — por isso o aviso de
// "confirme casos condicionais" sempre acompanha a resposta).

const FONTE = "buscadorncm.com.br";

export default async (req) => {
  const url = new URL(req.url);
  const ncm = (url.searchParams.get("ncm") || "").replace(/\D/g, "");

  if (ncm.length !== 8) {
    return json({ erro: "Informe um NCM com 8 dígitos (ex.: 61091000 ou 6109.10.00)." }, 400);
  }

  let html;
  try {
    const resp = await fetch(`https://buscadorncm.com.br/ncm/${ncm}`, {
      headers: {
        "User-Agent": "Mozilla/5.0 (compatible; FiqueDeOlhoContdias/1.0; +https://radar-fiscal-contdias.netlify.app)",
      },
    });
    if (!resp.ok) throw new Error(`status ${resp.status}`);
    html = await resp.text();
  } catch (e) {
    return json({ erro: "Não consegui consultar a fonte agora (buscadorncm.com.br). Tente de novo em instantes." }, 502);
  }

  const tituloMatch = html.match(/<title>(.*?)<\/title>/s);
  const titulo = tituloMatch
    ? tituloMatch[1].replace(/&amp;/g, "&").replace(/&mdash;/g, "—").replace(/&middot;/g, "·").trim()
    : `NCM ${ncm}`;

  let respostaCst = null;
  let respostaReforma = null;
  const blocos = html.matchAll(/<script type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/g);
  for (const m of blocos) {
    let dados;
    try {
      dados = JSON.parse(m[1]);
    } catch {
      continue;
    }
    if (dados && dados["@type"] === "FAQPage") {
      for (const q of dados.mainEntity || []) {
        const nome = q.name || "";
        if (nome.includes("CST e cClassTrib")) respostaCst = q.acceptedAnswer?.text || null;
        if (nome.startsWith("Como fica") && nome.includes("Reforma Tribut")) {
          respostaReforma = q.acceptedAnswer?.text || null;
        }
      }
    }
  }

  if (!respostaCst) {
    return json({
      encontrado: false,
      ncm,
      titulo,
      mensagem:
        "Não encontrei a informação de cClassTrib/CST para este NCM na fonte consultada — pode ser um código pouco " +
        "usual, inexistente, ou o enquadramento exige análise caso a caso. Confirme diretamente ou peça uma " +
        "conferência completa se for para uma planilha de produtos.",
      fonte: FONTE,
    });
  }

  const cclasstribMatch = respostaCst.match(/cClassTrib\s+(\d{6})/);
  const cstMatch = respostaCst.match(/CST IBS\/CBS\s+(\d{3})/);
  const cclasstrib = cclasstribMatch ? cclasstribMatch[1] : null;
  const cst = cstMatch ? cstMatch[1] : null;
  const regimeGeral = cst === "000";

  return json({
    encontrado: true,
    ncm,
    titulo,
    cclasstrib,
    cst,
    regimeGeral,
    respostaResumo: respostaCst,
    respostaDetalhe: respostaReforma,
    fonte: FONTE,
    consultadoEm: new Date().toISOString(),
  });
};

function json(corpo, status = 200) {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      // cache curto na CDN da Netlify — reduz carga repetida na fonte sem
      // deixar a resposta velha por muito tempo
      "cache-control": "public, max-age=1800",
    },
  });
};
