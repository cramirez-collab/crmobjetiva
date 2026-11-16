// Objetiva Mail · lógica del servidor de rastreo (sin dependencias de Deno
// para poder probarla en Node). index.ts la conecta con Supabase.

export type Tipo = 'apertura' | 'clic'
export type Descartado = 'propio' | 'duplicado' | 'bot' | null

export interface Rastreo {
  id: string
  propietario: string
  meta_cifrada: string | null
  enlaces_hash: string[]
  creado_en: string
}

export interface Evento {
  rastreo_id: string
  tipo: Tipo
  enlace: number | null
  ocurrido_en: string
  origen: string
  pais: string | null
  ip_hash: string | null
  descartado: Descartado
}

export interface Store {
  obtenerRastreo(id: string): Promise<Rastreo | null>
  /** false si el id ya existía */
  crearRastreo(r: Rastreo): Promise<boolean>
  ultimoEvento(rastreoId: string, tipo: Tipo, ipHash: string): Promise<Evento | null>
  insertarEvento(e: Evento): Promise<void>
  listarRastreos(propietario: string, desdeIso: string, limite: number): Promise<Rastreo[]>
  listarEventos(ids: string[]): Promise<Evento[]>
  /** Marca como 'propio' los eventos sin descartar de esos ids (del propietario) desde la fecha dada */
  marcarPropios(propietario: string, ids: string[], desdeIso: string): Promise<number>
}

export interface Config {
  claveInstalacion: string
  pimienta: string
  ahora?: () => number
}

export const DUPLICADO_MS = 30_000
export const VENTANA_PROPIO_MS = 30_000
export const MADURACION_MS = 20_000
export const MAX_ENLACES = 100
export const MAX_META = 20_000

const ID_RE = /^[a-f0-9]{32}$/
const HEX64_RE = /^[a-f0-9]{64}$/

const GIF = Uint8Array.from(
  atob('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'),
  (c) => c.charCodeAt(0),
)

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'content-type, x-clave-instalacion, authorization, apikey',
  'Access-Control-Max-Age': '86400',
}

export async function sha256Hex(texto: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(texto))
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, '0')).join('')
}

// ---------------------------------------------------------------- clasificación

export function origenDe(ua: string): string {
  if (/GoogleImageProxy|ggpht\.com/i.test(ua)) return 'gmail'
  if (/YahooMailProxy/i.test(ua)) return 'yahoo'
  if (/Microsoft Outlook|ms-office|Outlook-iOS|Outlook-Android|MSOffice/i.test(ua)) return 'outlook'
  // Apple Mail (y su Protección de Privacidad) usa WebKit sin el token "Safari".
  if (/AppleWebKit/i.test(ua) && !/Safari|Chrome|Edg|Firefox/i.test(ua)) return 'apple'
  return 'otro'
}

const BOT_RE =
  /bot\b|crawler|spider|preview|Barracuda|Mimecast|Proofpoint|Safelinks|ZScaler|Forcepoint|Symantec|Trend ?Micro|python-requests|python-urllib|curl\/|wget|Go-http-client|okhttp|HeadlessChrome|facebookexternalhit|Slackbot|WhatsApp|TelegramBot|Discordbot|LinkedInBot/i

export function esBot(ua: string, metodo: string): boolean {
  if (metodo === 'HEAD') return true
  if (!ua) return true
  return BOT_RE.test(ua)
}

/** El navegador del propio remitente cargando el píxel directo dentro de Gmail. */
export function esPropioDirecto(ua: string, referer: string): boolean {
  if (/GoogleImageProxy|ggpht\.com/i.test(ua)) return false
  return /^https:\/\/mail\.google\.com\//i.test(referer)
}

function ipDe(req: Request): string {
  const h = req.headers
  const xff = h.get('x-forwarded-for')
  return (h.get('cf-connecting-ip') || (xff ? xff.split(',')[0] : '') || h.get('x-real-ip') || '').trim()
}

// ---------------------------------------------------------------- respuestas

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...CORS, 'Content-Type': 'application/json; charset=utf-8' },
  })
}

function gif(): Response {
  return new Response(GIF, {
    headers: {
      'Content-Type': 'image/gif',
      'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
      Pragma: 'no-cache',
      Expires: '0',
    },
  })
}

function escHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
}

function paginaContinuar(destino: string): Response {
  const d = escHtml(destino)
  const body = `<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Continuar</title></head>
<body style="margin:0;background:#fff;font-family:system-ui,sans-serif;color:#4A4A4A;display:flex;min-height:100vh;align-items:center;justify-content:center">
<div style="max-width:480px;padding:24px;border:1px solid #E5E5E5;border-radius:12px;margin:16px">
<p style="margin:0 0 8px;color:#002C63;font-weight:600">Vas a salir a otro sitio</p>
<p style="margin:0 0 16px;word-break:break-all;color:#9E9E9E">${d}</p>
<a href="${d}" rel="noopener noreferrer" style="display:inline-block;background:#02B381;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none">Continuar</a>
</div></body></html>`
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8' } })
}

// ---------------------------------------------------------------- handler

export function crearHandler(store: Store, cfg: Config) {
  const ahora = cfg.ahora ?? (() => Date.now())

  async function registrarEvento(req: Request, r: Rastreo, tipo: Tipo, enlace: number | null) {
    const ua = req.headers.get('user-agent') || ''
    const referer = req.headers.get('referer') || ''
    const ip = ipDe(req)
    const ipHash = ip ? (await sha256Hex(cfg.pimienta + '|' + ip)).slice(0, 32) : null
    const ts = ahora()

    let descartado: Descartado = null
    if (esPropioDirecto(ua, referer)) descartado = 'propio'
    else if (esBot(ua, req.method)) descartado = 'bot'
    else if (ipHash) {
      const ultimo = await store.ultimoEvento(r.id, tipo, ipHash)
      if (ultimo && ultimo.descartado !== 'bot' && ts - Date.parse(ultimo.ocurrido_en) < DUPLICADO_MS &&
          (tipo === 'apertura' || ultimo.enlace === enlace)) {
        descartado = 'duplicado'
      }
    }

    await store.insertarEvento({
      rastreo_id: r.id,
      tipo,
      enlace,
      ocurrido_en: new Date(ts).toISOString(),
      origen: origenDe(ua),
      pais: req.headers.get('cf-ipcountry') || req.headers.get('x-country') || null,
      ip_hash: ipHash,
      descartado,
    })
  }

  async function leerJson(req: Request): Promise<Record<string, unknown> | null> {
    try {
      const b = await req.json()
      return b && typeof b === 'object' ? (b as Record<string, unknown>) : null
    } catch {
      return null
    }
  }

  async function propietarioDe(token: unknown): Promise<string | null> {
    if (typeof token !== 'string' || !HEX64_RE.test(token)) return null
    return sha256Hex('objetiva-mail|' + token)
  }

  return async function handler(req: Request): Promise<Response> {
    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS })

    const url = new URL(req.url)
    // Acepta /functions/v1/correo-rastreo/<ruta> o /<ruta>
    const ruta = url.pathname.replace(/^.*?\/correo-rastreo(?=\/|$)/, '') || '/'
    const partes = ruta.split('/').filter(Boolean)

    try {
      // ---------- píxel de apertura (público)
      if ((req.method === 'GET' || req.method === 'HEAD') && partes[0] === 'p' && partes.length === 2) {
        const id = partes[1].replace(/\.(gif|png)$/i, '')
        if (ID_RE.test(id)) {
          const r = await store.obtenerRastreo(id)
          if (r) await registrarEvento(req, r, 'apertura', null)
        }
        return gif()
      }

      // ---------- redirección de enlace (pública)
      if ((req.method === 'GET' || req.method === 'HEAD') && partes[0] === 'l' && partes.length === 3) {
        const id = partes[1]
        const n = Number(partes[2])
        const destino = url.searchParams.get('u') || ''
        let destinoUrl: URL
        try {
          destinoUrl = new URL(destino)
        } catch {
          return new Response('Enlace inválido', { status: 400 })
        }
        if (destinoUrl.protocol !== 'http:' && destinoUrl.protocol !== 'https:') {
          return new Response('Enlace inválido', { status: 400 })
        }
        if (!ID_RE.test(id) || !Number.isInteger(n) || n < 0 || n >= MAX_ENLACES) return paginaContinuar(destino)

        const r = await store.obtenerRastreo(id)
        const hash = await sha256Hex(destino)
        // Solo redirige en automático a destinos que la extensión registró (evita redirección abierta).
        if (!r || !r.enlaces_hash.includes(hash)) return paginaContinuar(destino)

        await registrarEvento(req, r, 'clic', n)
        return new Response(null, {
          status: 302,
          headers: { Location: destino, 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer' },
        })
      }

      if (req.method !== 'POST') return json({ error: 'no encontrado' }, 404)

      // ---------- registrar un correo enviado (extensión)
      if (ruta === '/registrar') {
        if (!cfg.claveInstalacion || req.headers.get('x-clave-instalacion') !== cfg.claveInstalacion) {
          return json({ error: 'clave de instalación inválida' }, 401)
        }
        const b = await leerJson(req)
        if (!b) return json({ error: 'json inválido' }, 400)
        const propietario = await propietarioDe(b.token)
        if (!propietario) return json({ error: 'token inválido' }, 400)
        if (typeof b.id !== 'string' || !ID_RE.test(b.id)) return json({ error: 'id inválido' }, 400)
        const meta = b.meta == null ? null : b.meta
        if (meta !== null && (typeof meta !== 'string' || meta.length > MAX_META)) {
          return json({ error: 'meta inválida' }, 400)
        }
        const enlaces = Array.isArray(b.enlaces) ? b.enlaces : []
        if (enlaces.length > MAX_ENLACES || !enlaces.every((h) => typeof h === 'string' && HEX64_RE.test(h))) {
          return json({ error: 'enlaces inválidos' }, 400)
        }

        const creado = await store.crearRastreo({
          id: b.id,
          propietario,
          meta_cifrada: meta as string | null,
          enlaces_hash: enlaces as string[],
          creado_en: new Date(ahora()).toISOString(),
        })
        if (!creado) {
          const existente = await store.obtenerRastreo(b.id)
          // Reintento idempotente del mismo dueño = ok; id ajeno = conflicto.
          if (existente?.propietario === propietario) return json({ ok: true })
          return json({ error: 'id en uso' }, 409)
        }
        return json({ ok: true }, 201)
      }

      // ---------- mis correos (solo los del dueño del token)
      if (ruta === '/mis-correos') {
        const b = await leerJson(req)
        const propietario = await propietarioDe(b?.token)
        if (!propietario) return json({ error: 'token inválido' }, 400)
        const dias = Math.min(Math.max(Number(b?.dias) || 180, 1), 365)
        const limite = Math.min(Math.max(Number(b?.limite) || 300, 1), 1000)
        const desde = new Date(ahora() - dias * 86_400_000).toISOString()

        const rastreos = await store.listarRastreos(propietario, desde, limite)
        const eventos = rastreos.length ? await store.listarEventos(rastreos.map((r) => r.id)) : []
        const corte = ahora() - MADURACION_MS
        const porId = new Map<string, Evento[]>()
        for (const e of eventos) {
          if (e.descartado) continue
          if (Date.parse(e.ocurrido_en) > corte) continue // espera por si resulta ser una vista propia
          const arr = porId.get(e.rastreo_id) ?? []
          arr.push(e)
          porId.set(e.rastreo_id, arr)
        }

        const correos = rastreos.map((r) => {
          const evs = (porId.get(r.id) ?? []).sort((a, b) => b.ocurrido_en.localeCompare(a.ocurrido_en))
          const ap = evs.filter((e) => e.tipo === 'apertura')
          const cl = evs.filter((e) => e.tipo === 'clic')
          return {
            id: r.id,
            meta: r.meta_cifrada,
            creado_en: r.creado_en,
            aperturas: ap.length,
            clics: cl.length,
            ultima_apertura: ap[0]?.ocurrido_en ?? null,
            ultimo_clic: cl[0]?.ocurrido_en ?? null,
            eventos: evs.slice(0, 30).map((e) => ({
              tipo: e.tipo,
              en: e.ocurrido_en,
              origen: e.origen,
              pais: e.pais,
              enlace: e.enlace,
            })),
          }
        })
        return json({ correos, servidor_ahora: new Date(ahora()).toISOString() })
      }

      // ---------- el remitente abrió su propio hilo: descartar aperturas recientes
      if (ruta === '/propio') {
        const b = await leerJson(req)
        const propietario = await propietarioDe(b?.token)
        if (!propietario) return json({ error: 'token inválido' }, 400)
        const ids = Array.isArray(b?.ids) ? (b!.ids as unknown[]).filter((x): x is string => typeof x === 'string' && ID_RE.test(x)) : []
        if (!ids.length || ids.length > 200) return json({ error: 'ids inválidos' }, 400)
        const desde = new Date(ahora() - VENTANA_PROPIO_MS).toISOString()
        const marcados = await store.marcarPropios(propietario, ids, desde)
        return json({ ok: true, marcados })
      }

      return json({ error: 'no encontrado' }, 404)
    } catch (err) {
      console.error('[correo-rastreo]', err)
      // El píxel nunca debe fallar visualmente
      if (partes[0] === 'p') return gif()
      return json({ error: 'error interno' }, 500)
    }
  }
}
