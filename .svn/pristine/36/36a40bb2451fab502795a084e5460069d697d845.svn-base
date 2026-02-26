import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
// 如需启用 HTTPS 自定义证书，取消下行注释并配置证书路径
// import fs from 'fs'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  define: {
    // 强制定义环境变量，确保内网穿透时使用代理
    'import.meta.env.VITE_SUPABASE_URL': JSON.stringify('/supabase'),
  },
  server: {
    port: 3000,
    host: '0.0.0.0', // 允许局域网访问
    allowedHosts: true,
    // 启用 HTTPS（可选：使用自签名证书支持手机相机功能）
    // 如需启用，请运行: npx vite --https
    // 或者配置自定义证书:
    // https: {
    //   key: fs.readFileSync('path/to/key.pem'),
    //   cert: fs.readFileSync('path/to/cert.pem'),
    // },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8080',  // 使用 IPv4 地址，避免 IPv6 解析问题
        changeOrigin: true,
      },
      // 代理 Supabase 请求，支持内网穿透访问
      '/supabase': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/supabase/, ''),
      },
    },
  },
})
