import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/kakao-token': {
        target: 'https://kauth.kakao.com',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/kakao-token/, '/oauth/token'),
      },
      '/kakao-api': {
        target: 'https://kapi.kakao.com',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/kakao-api/, ''),
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-antd': ['antd', '@ant-design/icons'],
          'vendor-charts': ['@ant-design/charts'],
          'vendor-supabase': ['@supabase/supabase-js'],
        },
      },
    },
  },
})
