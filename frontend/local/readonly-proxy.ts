import type { Plugin, Connect } from 'vite'
import { createHash, randomUUID } from 'node:crypto'
import { mkdir, appendFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { Readable } from 'node:stream'
import http from 'node:http'

export function allowedApiPath(path: string) {
  return (
    /^\/api\/room-jobs(?:\/(?:options|sources|[A-Za-z0-9_-]+(?:\/(?:video|spatial-context))?))?$/.test(
      path,
    ) ||
    /^\/api\/catalog\/(?:scenes\/[A-Za-z0-9_-]+\/rooms|rooms\/\d+\/(?:points|assets))$/.test(path)
  )
}
export function requestLog(
  trace: string,
  ok: boolean,
  duration: number,
  method = 'GET',
  requestId?: string,
  jobId?: string,
) {
  return {
    schema_version: 1,
    event_id: randomUUID(),
    ts: new Date().toISOString(),
    pid: process.pid,
    trace_id: trace,
    ...(requestId ? { request_id: requestId } : {}),
    ...(jobId ? { job_id: jobId } : {}),
    operation: method === 'POST' ? 'frontend.test_submit' : 'frontend.read_proxy',
    stage: 'http',
    event: ok ? 'success' : 'failure',
    duration_ms: duration,
    ...(!ok ? { error_code: method === 'POST' ? 'test_submit_failed' : 'read_proxy_failed' } : {}),
  }
}
export function validateTestBody(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('invalid')
  const body = value as Record<string, unknown>,
    keys = [
      'scene_code',
      'room_id',
      'asset_version',
      'layout_version_id',
      'style_preset',
      'preset',
      'camera_mode',
      'confirm_render',
    ]
  if (
    Object.keys(body).sort().join(',') !== keys.sort().join(',') ||
    body.room_id !== 'Room8' ||
    body.style_preset !== 'r3' ||
    body.preset !== 'test' ||
    body.confirm_render !== true ||
    !['overview', 'closeup'].includes(String(body.camera_mode)) ||
    !Number.isInteger(body.layout_version_id) ||
    Number(body.layout_version_id) < 1 ||
    ![body.scene_code, body.asset_version].every(
      (v) => typeof v === 'string' && /^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/.test(v),
    )
  )
    throw Error('invalid')
  return body
}
function tunnelRead(signed: URL, tunnel: string): Promise<Buffer> {
  const connection = new URL(tunnel)
  if (connection.protocol !== 'http:' || connection.hostname !== '127.0.0.1') throw Error('tunnel')
  return new Promise((accept, reject) => {
    const request = http.get(
      {
        hostname: connection.hostname,
        port: connection.port,
        path: signed.pathname + signed.search,
        headers: { Host: signed.host },
        timeout: 10000,
      },
      (response) => {
        if (response.statusCode !== 200) {
          response.resume()
          reject(Error('asset'))
          return
        }
        const chunks: Buffer[] = []
        let size = 0
        response.on('data', (chunk: Buffer) => {
          size += chunk.length
          if (size > 32 * 1024 * 1024) {
            response.destroy()
            reject(Error('size'))
          } else chunks.push(chunk)
        })
        response.on('end', () => accept(Buffer.concat(chunks)))
        response.on('error', reject)
      },
    )
    request.on('timeout', () => request.destroy(Error('timeout')))
    request.on('error', reject)
  })
}
export function readonlyProxy(env: Record<string, string>): Plugin {
  const target = env.ROOM_API_TARGET
  const disabled = process.env.ROOM_READONLY_DISABLED === '1'
  const root = resolve('..', 'data', 'logs', 'operations')
  const name = `${new Date().toISOString().slice(0, 10)}-${process.pid}-${randomUUID().slice(0, 8)}-0.jsonl`
  const read = (path: string, trace: string) =>
    fetch(new URL(path, target), {
      headers: { 'X-Trace-ID': trace },
      signal: AbortSignal.timeout(10000),
      redirect: 'error',
    })
  const middleware: Connect.NextHandleFunction = async (req, res, next) => {
    const url = new URL(req.url ?? '/', 'http://localhost')
    if (
      !url.pathname.startsWith('/api/') &&
      !url.pathname.startsWith('/room-assets/') &&
      url.pathname !== '/local-service/status'
    )
      return next()
    const raw = req.headers['x-trace-id']
    const trace =
      typeof raw === 'string' && /^[A-Za-z0-9_.:-]{1,96}$/.test(raw) ? raw : randomUUID()
    const start = performance.now()
    let ok = false
    let upstreamRequestId: string | undefined
    let acceptedJobId: string | undefined
    res.setHeader('X-Trace-ID', trace)
    res.setHeader('Cache-Control', 'no-store')
    res.on('finish', () => {
      if (url.pathname === '/local-service/status') return
      void mkdir(root, { recursive: true })
        .then(() =>
          appendFile(
            resolve(root, name),
            JSON.stringify(
              requestLog(
                trace,
                ok,
                performance.now() - start,
                req.method,
                upstreamRequestId,
                acceptedJobId,
              ),
            ) + '\n',
          ),
        )
        .catch(() => {})
    })
    const fail = (code: number, reason: string) => {
      res.statusCode = code
      res.setHeader('Content-Type', 'application/json')
      res.end(JSON.stringify({ code: reason, trace_id: trace }))
    }
    const submission = req.method === 'POST' && url.pathname === '/api/room-jobs' && !url.search
    if (!['GET', 'HEAD'].includes(req.method ?? '') && !submission) return fail(405, 'read_only')
    if (!/^(localhost|127\.0\.0\.1)(:\d+)?$/.test(req.headers.host ?? ''))
      return fail(403, 'local_only')
    if (req.headers.origin && !/^http:\/\/(localhost|127\.0\.0\.1):\d+$/.test(req.headers.origin))
      return fail(403, 'origin_rejected')
    if (url.pathname === '/local-service/status') {
      res.setHeader('Content-Type', 'application/json')
      res.end(
        JSON.stringify({
          configured: Boolean(target) && !disabled,
          read_only: env.ROOM_TEST_SUBMIT_ENABLED !== '1',
          test_submit_enabled: env.ROOM_TEST_SUBMIT_ENABLED === '1' && !disabled,
          spatial_context_enabled: env.ROOM_SPATIAL_CONTEXT_ENABLED === '1' && !disabled,
        }),
      )
      return
    }
    if (!target || disabled) return fail(503, 'service_not_configured')
    if (submission) {
      if (env.ROOM_TEST_SUBMIT_ENABLED !== '1') return fail(403, 'submission_not_approved')
      if (req.headers.origin !== `http://${req.headers.host}`) return fail(403, 'origin_rejected')
      const key = req.headers['idempotency-key']
      if (typeof key !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_-]{7,95}$/.test(key))
        return fail(422, 'invalid_submission_key')
      try {
        const chunks: Buffer[] = []
        let length = 0
        for await (const chunk of req) {
          length += chunk.length
          if (length > 4096) return fail(413, 'submission_too_large')
          chunks.push(Buffer.from(chunk))
        }
        let body: Record<string, unknown>
        try {
          body = validateTestBody(JSON.parse(Buffer.concat(chunks).toString('utf-8')))
        } catch {
          return fail(422, 'invalid_test_configuration')
        }
        const upstream = await fetch(new URL('/api/room-jobs', target), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Idempotency-Key': key,
            'X-Trace-ID': trace,
          },
          body: JSON.stringify(body),
          signal: AbortSignal.timeout(12000),
          redirect: 'error',
        })
        const requestId = upstream.headers.get('X-Request-ID')
        if (requestId && /^[A-Za-z0-9_.:-]{1,96}$/.test(requestId)) {
          res.setHeader('X-Request-ID', requestId)
          upstreamRequestId = requestId
        }
        const response: unknown = await upstream.json()
        if (!response || typeof response !== 'object' || Array.isArray(response))
          return fail(502, 'submission_outcome_unknown')
        const bodyResponse = response as Record<string, unknown>
        res.statusCode = upstream.status
        res.setHeader('Content-Type', 'application/json')
        ok = upstream.ok
        if (!upstream.ok) {
          const code = (response as { detail?: { code?: unknown } }).detail?.code
          return res.end(
            JSON.stringify({
              detail: {
                code:
                  typeof code === 'string' && /^[a-z_]{1,96}$/.test(code)
                    ? code
                    : 'submission_failed',
              },
            }),
          )
        }
        if (
          typeof bodyResponse.job_id === 'string' &&
          /^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/.test(bodyResponse.job_id)
        )
          acceptedJobId = bodyResponse.job_id
        return res.end(JSON.stringify(response))
      } catch {
        return fail(502, 'submission_outcome_unknown')
      }
    }
    try {
      if (url.pathname.startsWith('/api/')) {
        if (!allowedApiPath(url.pathname)) return fail(403, 'route_not_allowed')
        for (const key of url.searchParams.keys())
          if (!['scene_code', 'room_id', 'layout_version_id', 'limit', 'offset'].includes(key))
            return fail(400, 'query_not_allowed')
        const headers: Record<string, string> = { 'X-Trace-ID': trace }
        if (typeof req.headers.range === 'string' && /^bytes=\d*-\d*$/.test(req.headers.range))
          headers.Range = req.headers.range
        const upstream = await fetch(new URL(url.pathname + url.search, target), {
          method: req.method,
          headers,
          signal: AbortSignal.timeout(15000),
          redirect: 'error',
        })
        if (!upstream.ok) {
          await upstream.body?.cancel()
          return fail(upstream.status, 'upstream_read_failed')
        }
        res.statusCode = upstream.status
        for (const key of [
          'content-type',
          'content-length',
          'content-range',
          'accept-ranges',
          'etag',
          'x-request-id',
        ]) {
          const value = upstream.headers.get(key)
          if (value) res.setHeader(key, value)
        }
        ok = true
        const incomingRequestId = upstream.headers.get('X-Request-ID')
        if (incomingRequestId && /^[A-Za-z0-9_.:-]{1,96}$/.test(incomingRequestId))
          upstreamRequestId = incomingRequestId
        if (req.method === 'HEAD' || !upstream.body) res.end()
        else
          Readable.fromWeb(upstream.body as never)
            .on('error', () => res.destroy())
            .pipe(res)
        return
      }
      if (!/^\/room-assets\/\d+$/.test(url.pathname) || url.search)
        return fail(400, 'asset_request_invalid')
      const id = Number(url.pathname.split('/').at(-1))
      const sourceResponse = await read('/api/room-jobs/sources', trace)
      if (!sourceResponse.ok) return fail(503, 'sources_unavailable')
      const sources = (await sourceResponse.json()) as { sources: { database_room_id: number }[] }
      type Asset = {
        id: number
        kind: string
        sha256: string
        uploaded: boolean
        size_bytes: number
      }
      let asset: Asset | undefined
      for (const room of sources.sources.slice(0, 100)) {
        const response = await read(`/api/catalog/rooms/${room.database_room_id}/assets`, trace)
        if (!response.ok) continue
        const list = (await response.json()) as { assets: Asset[] }
        asset = list.assets.find(
          (a) => a.id === id && a.uploaded && ['room_glb', 'room_preview'].includes(a.kind),
        )
        if (asset) break
      }
      if (!asset || !/^[a-f0-9]{64}$/.test(asset.sha256) || asset.size_bytes > 32 * 1024 * 1024)
        return fail(404, 'asset_not_registered')
      const share = await read(`/api/catalog/assets/${id}/share`, trace)
      if (!share.ok) return fail(502, 'share_unavailable')
      const signed = new URL(((await share.json()) as { url: string }).url)
      if (
        signed.hostname !== new URL(target).hostname ||
        signed.port !== '9000' ||
        signed.protocol !== 'http:'
      )
        return fail(502, 'asset_origin_rejected')
      let bytes: Buffer
      if (env.ROOM_MINIO_TUNNEL) bytes = await tunnelRead(signed, env.ROOM_MINIO_TUNNEL)
      else {
        const response = await fetch(signed, {
          signal: AbortSignal.timeout(8000),
          redirect: 'error',
        })
        if (!response.ok) return fail(502, 'asset_unreachable')
        if (Number(response.headers.get('content-length')) > 32 * 1024 * 1024) {
          await response.body?.cancel()
          return fail(502, 'asset_too_large')
        }
        bytes = Buffer.from(await response.arrayBuffer())
      }
      if (
        bytes.length !== asset.size_bytes ||
        createHash('sha256').update(bytes).digest('hex') !== asset.sha256
      )
        return fail(502, 'asset_integrity_failed')
      res.setHeader('Content-Type', asset.kind === 'room_glb' ? 'model/gltf-binary' : 'image/png')
      res.setHeader('Content-Length', bytes.length)
      res.setHeader('X-Asset-SHA256', asset.sha256)
      ok = true
      res.end(req.method === 'HEAD' ? undefined : bytes)
    } catch {
      fail(502, 'resource_unreachable')
    }
  }
  return {
    name: 'burnscape-local-readonly',
    configureServer(server) {
      server.middlewares.use(middleware)
    },
    configurePreviewServer(server) {
      server.middlewares.use(middleware)
    },
  }
}
