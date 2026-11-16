// Objetiva Mail · Edge Function de Supabase
// Desplegar SIN verificación JWT (el píxel y los enlaces son públicos):
//   supabase functions deploy correo-rastreo --no-verify-jwt
// Secretos requeridos:
//   supabase secrets set CORREO_CLAVE_INSTALACION=... CORREO_PIMIENTA=...

import { createClient } from 'npm:@supabase/supabase-js@2.50.3'
import { crearHandler, type Evento, type Rastreo, type Store, type Tipo } from './handler.ts'

declare const Deno: {
  env: { get(k: string): string | undefined }
  serve(h: (req: Request) => Response | Promise<Response>): void
}

const db = createClient(Deno.env.get('SUPABASE_URL') ?? '', Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '', {
  auth: { autoRefreshToken: false, persistSession: false },
})

const store: Store = {
  async obtenerRastreo(id) {
    const { data, error } = await db.from('correo_rastreo').select('*').eq('id', id).maybeSingle()
    if (error) throw error
    return (data as Rastreo) ?? null
  },
  async crearRastreo(r) {
    const { error } = await db.from('correo_rastreo').insert(r)
    if (!error) return true
    if (error.code === '23505') return false
    throw error
  },
  async ultimoEvento(rastreoId: string, tipo: Tipo, ipHash: string) {
    const { data, error } = await db
      .from('correo_evento')
      .select('*')
      .eq('rastreo_id', rastreoId)
      .eq('tipo', tipo)
      .eq('ip_hash', ipHash)
      .order('ocurrido_en', { ascending: false })
      .limit(1)
      .maybeSingle()
    if (error) throw error
    return (data as Evento) ?? null
  },
  async insertarEvento(e) {
    const { error } = await db.from('correo_evento').insert(e)
    if (error) throw error
  },
  async listarRastreos(propietario, desdeIso, limite) {
    const { data, error } = await db
      .from('correo_rastreo')
      .select('*')
      .eq('propietario', propietario)
      .gte('creado_en', desdeIso)
      .order('creado_en', { ascending: false })
      .limit(limite)
    if (error) throw error
    return (data as Rastreo[]) ?? []
  },
  async listarEventos(ids) {
    const todos: Evento[] = []
    for (let i = 0; i < ids.length; i += 100) {
      const { data, error } = await db
        .from('correo_evento')
        .select('*')
        .in('rastreo_id', ids.slice(i, i + 100))
        .is('descartado', null)
        .order('ocurrido_en', { ascending: false })
        .limit(5000)
      if (error) throw error
      todos.push(...((data as Evento[]) ?? []))
    }
    return todos
  },
  async marcarPropios(propietario, ids, desdeIso) {
    const { data: propios, error: e1 } = await db
      .from('correo_rastreo')
      .select('id')
      .eq('propietario', propietario)
      .in('id', ids)
    if (e1) throw e1
    const suyos = (propios ?? []).map((r: { id: string }) => r.id)
    if (!suyos.length) return 0
    const { data, error } = await db
      .from('correo_evento')
      .update({ descartado: 'propio' })
      .in('rastreo_id', suyos)
      .gte('ocurrido_en', desdeIso)
      .is('descartado', null)
      .select('id')
    if (error) throw error
    return data?.length ?? 0
  },
}

Deno.serve(
  crearHandler(store, {
    claveInstalacion: Deno.env.get('CORREO_CLAVE_INSTALACION') ?? '',
    pimienta: Deno.env.get('CORREO_PIMIENTA') ?? '',
  }),
)
