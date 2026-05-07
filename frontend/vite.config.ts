import { defineConfig, loadEnv, createLogger } from 'vite'
import react from '@vitejs/plugin-react'

// WS 프록시 ECONNRESET 노이즈 제거 (백엔드 재시작 시 정상 발생)
const logger = createLogger()
const _warn = logger.warn.bind(logger)
logger.warn = (msg, opts) => {
  if (msg.includes('ws proxy socket error') || msg.includes('ECONNRESET')) return
  _warn(msg, opts)
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendPort = env.BACKEND_PORT || '8000'
  const frontendPort = parseInt(env.FRONTEND_PORT || '5173')

  return {
    plugins: [react()],
    customLogger: logger,
    server: {
      port: frontendPort,
      proxy: {
        '/api': {
          target: `http://localhost:${backendPort}`,
          changeOrigin: true,
        },
        '/ws': {
          target: `ws://localhost:${backendPort}`,
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
