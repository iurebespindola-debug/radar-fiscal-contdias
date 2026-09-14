// Função serverless do Netlify (roda no servidor deles, não no navegador de
// quem acessa) — existe porque nenhuma das duas fontes abaixo permite
// chamada direta do navegador de outro site (bloqueio de CORS).
//
// Consulta DUAS fontes, em paralelo, e cruza:
//   1) buscadorncm.com.br — agregador especializado; dá o cClassTrib/CST
//      sugerido (extraído dos dados estruturados que o site já publica
//      para SEO). NÃO é fonte oficial do governo.
//   2) piloto-cbs.tributos.gov.br — API de dados abertos da própria
//      Calculadora oficial da Receita Federal/Serpro. Não devolve
//      cClassTrib isolado (o cálculo oficial completo exige simular a
//      operação inteira, não só o NCM — por isso não existe um "consulte
//      só o NCM" oficial), mas confirma a descrição oficial do NCM
//      (capítulo/posição/subitem) e se o produto é tributado pelo
//      Imposto Seletivo — um dado que o agregador não traz.
//
// O resultado final deixa claro qual veio de qual fonte, para quem usa a
// ferramenta saber o que é "sugestão de agregador" e o que é "confirmado
// pela Receita Federal".

const FONTE_AGREGADOR = "buscadorncm.com.br";
const FONTE_OFICIAL = "Receita Federal/Serpro (piloto-cbs.tributos.gov.br)";

export default async (req) => {
  const url = new URL(req.url);
  const ncm = (url.searchParams.get("ncm") || "").replace(/\D/g, "");

  if (ncm.length !== 8) {
    return json({ erro: "Informe um NCM com 8 dígitos (ex.: 61091000 ou 6109.10.00)." }, 400);
  }

  const [agregador, oficial] = await Promise.all([
    consultarAgregador(ncm),
    consultarOficial(ncm),
  ]);

  if (agregador.erro) {
    return json({ erro: agregador.erro }, 502);
  }

  if (!agregador.respostaCst) {
    return json({
      encontrado: false,
      ncm,
      titulo: agregador.titulo,
      mensagem:
        "Não encontrei a informação de cClassTrib/CST para este NCM no agregador — pode ser um código pouco " +
        "usual, inexistente, ou o enquadramento exige análise caso a caso. Confirme diretamente ou peça uma " +
        "conferência completa se for para uma planilha de produtos.",
      oficial: oficial.dados || null,
      fonte: FONTE_AGREGADOR,
    });
  }

  return json({
    encontrado: true,
    ncm,
    titulo: agregador.titulo,
    cclasstrib: agregador.cclasstrib,
    cst: agregador.cst,
    regimeGeral: agregador.regimeGeral,
    semCodigoUnico: agregador.semCodigoUnico,
    respostaResumo: agregador.respostaCst,
    respostaDetalhe: agregador.respostaReforma,
    fonte: FONTE_AGREGADOR,
    oficial: oficial.dados || null,
    oficialErro: oficial.erro || null,
    fonteOficial: FONTE_OFICIAL,
    consultadoEm: new Date().toISOString(),
  });
};

// --- Fonte 1: agregador buscadorncm.com.br (dá o cClassTrib/CST sugerido) --

async function consultarAgregador(ncm) {
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
    return { erro: "Não consegui consultar a fonte agora (buscadorncm.com.br). Tente de novo em instantes." };
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
    return { titulo, respostaCst: null };
  }

  const cclasstribMatch = respostaCst.match(/cClassTrib\s+(\d{6})/);
  const cstMatch = respostaCst.match(/CST IBS\/CBS\s+(\d{3})/);
  const cclasstrib = cclasstribMatch ? cclasstribMatch[1] : null;
  const cst = cstMatch ? cstMatch[1] : null;

  // Alguns produtos (tipicamente sujeitos a Imposto Seletivo, como bebidas
  // alcoólicas e cigarros) não têm um cClassTrib único — o código varia
  // conforme a operação. Nesse caso "regimeGeral" fica null (nem
  // "regime geral" nem "benefício confirmado" — depende de caso a caso),
  // em vez de cair como false por padrão (o que sugeriria erradamente que
  // é sempre benefício/redução).
  let regimeGeral = null;
  if (cst !== null) regimeGeral = cst === "000";

  return {
    titulo,
    respostaCst,
    respostaReforma,
    cclasstrib,
    cst,
    regimeGeral,
    semCodigoUnico: cclasstrib === null && cst === null,
  };
}

// --- Fonte 2: API de dados abertos da Calculadora oficial (RFB/Serpro) ----
// Não dá cClassTrib isolado (precisaria simular a operação inteira), mas
// confirma a descrição oficial do NCM e se é tributado pelo Imposto
// Seletivo — cruzamento real com fonte do governo.

async function consultarOficial(ncm) {
  const hoje = new Date().toISOString().slice(0, 10);
  try {
    const resp = await fetch(
      `https://piloto-cbs.tributos.gov.br/servico/calculadora-consumo/api/calculadora/dados-abertos/ncm?data=${hoje}&ncm=${ncm}`,
      { headers: { "User-Agent": "Mozilla/5.0 (compatible; FiqueDeOlhoContdias/1.0)" } }
    );
    if (resp.status === 404) {
      return { erro: "NCM não encontrado na base oficial da Receita Federal para a data de hoje." };
    }
    if (!resp.ok) throw new Error(`status ${resp.status}`);
    const d = await resp.json();
    return {
      dados: {
        capitulo: d.capitulo || null,
        posicao: (d.posicao || "").replace(/<\/?i>/g, ""),
        subitem: d.subitem || null,
        tributadoPeloImpostoSeletivo: !!d.tributadoPeloImpostoSeletivo,
      },
    };
  } catch (e) {
    return { erro: "Não consegui confirmar com a Receita Federal agora (fonte oficial fora do ar ou indisponível)." };
  }
}

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
