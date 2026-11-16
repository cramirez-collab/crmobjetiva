// Pruebas: node --test supabase/functions/correo-rastreo/handler.test.ts
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { crearHandler, sha256Hex, origenDe, type Evento, type Rastreo, type Store } from './handler.ts'

function memoria() {
  const rastreos = new Map<string, Rastreo>()
  const eventos: Evento[] = []
  const store: Store = {
    async obtenerRastreo(id) { return rastreos.get(id) ?? null },
    async crearRastreo(r) { if (rastreos.has(r.id)) return false; rastreos.set(r.id, r); return true },
    async ultimoEvento(id, tipo, ip) {
      return [...eventos].reverse().find((e) => e.rastreo_id === id && e.tipo === tipo && e.ip_hash === ip) ?? null
    },
    async insertarEvento(e) { eventos.push(e) },
    async listarRastreos(p, desde, lim) {
      return [...rastreos.values()].filter((r) => r.propietario === p && r.creado_en >= desde).slice(0, lim)
    },
    async listarEventos(ids) { return eventos.filter((e) => ids.includes(e.rastreo_id) && !e.descartado) },
    async marcarPropios(p, ids, desde) {
      let n = 0
      for (const e of eventos) {
        const r = rastreos.get(e.rastreo_id)
        if (r?.propietario === p && ids.includes(e.rastreo_id) && e.ocurrido_en >= desde && !e.descartado) {
          e.descartado = 'propio'; n++
        }
      }
      return n
    },
  }
  return { store, rastreos, eventos }
}

const BASE = 'https://x.supabase.co/functions/v1/correo-rastreo'
const TOKEN = 'a'.repeat(64)
const OTRO = 'b'.repeat(64)
const ID = '0123456789abcdef0123456789abcdef'
const GMAIL_UA = 'Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko Firefox/11.0 (via ggpht.com GoogleImageProxy)'

function preparar() {
  let reloj = Date.parse('2026-11-16T12:00:00Z')
  const m = memoria()
  const h = crearHandler(m.store, { claveInstalacion: 'clave', pimienta: 'p', ahora: () => reloj })
  const avanzar = (ms: number) => { reloj += ms }
  const post = (ruta: string, body: unknown, clave = 'clave') =>
    h(new Request(BASE + ruta, { method: 'POST', headers: { 'content-type': 'application/json', 'x-clave-instalacion': clave }, body: JSON.stringify(body) }))
  const abrir = (id = ID, ua = GMAIL_UA, ip = '66.249.1.1', extra: Record<string, string> = {}) =>
    h(new Request(`${BASE}/p/${id}.gif`, { headers: { 'user-agent': ua, 'x-forwarded-for': ip, ...extra } }))
  return { h, m, avanzar, post, abrir }
}

test('registrar exige clave de instalación', async () => {
  const { post } = preparar()
  assert.equal((await post('/registrar', { id: ID, token: TOKEN }, 'mala')).status, 401)
  assert.equal((await post('/registrar', { id: ID, token: TOKEN })).status, 201)
  assert.equal((await post('/registrar', { id: ID, token: TOKEN })).status, 200, 'reintento idempotente')
  assert.equal((await post('/registrar', { id: ID, token: OTRO })).status, 409, 'id ajeno')
})

test('el servidor no guarda el token ni datos legibles', async () => {
  const { post, m } = preparar()
  await post('/registrar', { id: ID, token: TOKEN, meta: 'CIFRADO' })
  const r = m.rastreos.get(ID)!
  assert.notEqual(r.propietario, TOKEN)
  assert.equal(r.propietario, await sha256Hex('objetiva-mail|' + TOKEN))
  assert.equal(r.meta_cifrada, 'CIFRADO')
})

test('píxel: sin registrar no guarda nada, siempre responde GIF', async () => {
  const { abrir, m } = preparar()
  const res = await abrir()
  assert.equal(res.status, 200)
  assert.equal(res.headers.get('content-type'), 'image/gif')
  assert.equal(m.eventos.length, 0)
})

test('aperturas de Gmail cuentan, duplicados y bots no', async () => {
  const { post, abrir, avanzar, m } = preparar()
  await post('/registrar', { id: ID, token: TOKEN })
  await abrir()
  avanzar(5_000)
  await abrir() // duplicado (misma IP < 30 s)
  avanzar(60_000)
  await abrir() // segunda apertura real
  await abrir(ID, 'python-requests/2.31', '1.2.3.4') // bot
  assert.deepEqual(m.eventos.map((e) => e.descartado), [null, 'duplicado', null, 'bot'])
  assert.equal(m.eventos[0].origen, 'gmail')
  assert.ok(!m.eventos.some((e) => (e as unknown as Record<string, unknown>).ip), 'no guarda IP')

  avanzar(30_000)
  const r = await (await post('/mis-correos', { token: TOKEN })).json()
  assert.equal(r.correos.length, 1)
  assert.equal(r.correos[0].aperturas, 2)
})

test('carga directa desde mail.google.com = propio', async () => {
  const { post, abrir, m } = preparar()
  await post('/registrar', { id: ID, token: TOKEN })
  await abrir(ID, 'Mozilla/5.0 Chrome/130 Safari/537.36', '10.0.0.1', { referer: 'https://mail.google.com/mail/u/0/' })
  assert.equal(m.eventos[0].descartado, 'propio')
})

test('/propio descarta aperturas recientes solo del dueño; maduración oculta lo muy reciente', async () => {
  const { post, abrir, avanzar } = preparar()
  await post('/registrar', { id: ID, token: TOKEN })
  await abrir()
  // Otra persona no puede borrar mis aperturas
  assert.equal((await (await post('/propio', { token: OTRO, ids: [ID] })).json()).marcados, 0)
  // Recién ocurrida: aún no se muestra
  assert.equal((await (await post('/mis-correos', { token: TOKEN })).json()).correos[0].aperturas, 0)
  avanzar(2_000)
  assert.equal((await (await post('/propio', { token: TOKEN, ids: [ID] })).json()).marcados, 1)
  avanzar(60_000)
  assert.equal((await (await post('/mis-correos', { token: TOKEN })).json()).correos[0].aperturas, 0)
})

test('mis-correos solo devuelve los míos', async () => {
  const { post } = preparar()
  await post('/registrar', { id: ID, token: TOKEN })
  await post('/registrar', { id: 'f'.repeat(32), token: OTRO })
  const r = await (await post('/mis-correos', { token: TOKEN })).json()
  assert.deepEqual(r.correos.map((c: { id: string }) => c.id), [ID])
  assert.equal((await post('/mis-correos', { token: 'corto' })).status, 400)
})

test('enlaces: redirige solo a destinos registrados y cuenta el clic', async () => {
  const { h, post, avanzar } = preparar()
  const destino = 'https://objetiva.mx/propuesta?a=1&b=2'
  await post('/registrar', { id: ID, token: TOKEN, enlaces: [await sha256Hex(destino)] })
  const ir = (u: string, n = 0) =>
    h(new Request(`${BASE}/l/${ID}/${n}?u=${encodeURIComponent(u)}`, { headers: { 'user-agent': 'Mozilla/5.0 Chrome/130 Safari/537.36', 'x-forwarded-for': '8.8.8.8' } }))

  const ok = await ir(destino)
  assert.equal(ok.status, 302)
  assert.equal(ok.headers.get('location'), destino)

  const ajeno = await ir('https://malo.example/phish')
  assert.equal(ajeno.status, 200, 'no redirige: muestra página de continuar')
  assert.match(await ajeno.text(), /Continuar/)

  assert.equal((await ir('javascript:alert(1)')).status, 400)

  avanzar(30_000)
  const r = await (await post('/mis-correos', { token: TOKEN })).json()
  assert.equal(r.correos[0].clics, 1)
})

test('página de continuar escapa HTML', async () => {
  const { h } = preparar()
  const res = await h(new Request(`${BASE}/l/${ID}/0?u=${encodeURIComponent('https://x.com/"><script>')}`))
  const t = await res.text()
  assert.ok(!t.includes('<script>'))
})

test('origenDe', () => {
  assert.equal(origenDe(GMAIL_UA), 'gmail')
  assert.equal(origenDe('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko)'), 'apple')
  assert.equal(origenDe('Microsoft Office/16.0 (Windows NT 10.0; Microsoft Outlook 16.0.5)'), 'outlook')
  assert.equal(origenDe('Mozilla/5.0 Chrome/130 Safari/537.36'), 'otro')
})
