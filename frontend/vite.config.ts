import { defineConfig, loadEnv, createLogger } from 'vite'
import react from '@vitejs/plugin-react'

// WS 프록시 ECONNRESET 노이즈 제거 (백엔드 재시작 시 정상 발생)
const logger = createLogger()
const _suppress = (msg: string) =>
  msg.includes('ws proxy socket error') || msg.includes('ECONNRESET')
const _warn = logger.warn.bind(logger)
const _error = logger.error.bind(logger)
logger.warn  = (msg, opts) => { if (!_suppress(msg)) _warn(msg, opts) }
logger.error = (msg, opts) => { if (!_suppress(msg)) _error(msg, opts) }

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendPort = env.BACKEND_PORT || '8000'
  const frontendPort = parseInt(env.FRONTEND_PORT || '5173')

  return {
    plugins: [react()],
    customLogger: logger,
    server: {
      host: '127.0.0.1',
      port: frontendPort,
      strictPort: true,
      proxy: {
        '/api': {
          target: `http://127.0.0.1:${backendPort}`,
          changeOrigin: true,
        },
        '/ws': {
          target: `ws://127.0.0.1:${backendPort}`,
          changeOrigin: true,
          ws: true,
          configure: (proxy) => {
            proxy.on('error', () => {})
            proxy.on('proxyReqWs', (_proxyReq, _req, socket) => {
              socket.on('error', () => {})
            })
            proxy.on('open', (proxySocket) => {
              proxySocket.on('error', () => {})
            })
          },
        },
      },
    },
  }
})
