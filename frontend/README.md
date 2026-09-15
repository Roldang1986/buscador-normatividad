# Buscador de Normatividad Tributaria — Frontend

PWA (React + Vite, JavaScript plano) para el backend en `../app`. Ver la
sección "Frontend" del README raíz del repo para el detalle completo
(estructura, endpoints usados, variables de entorno).

## Desarrollo

```bash
npm install
cp .env.example .env   # ajustar VITE_API_BASE_URL si hace falta
npm run dev
```

## Build de producción

```bash
npm run build
```

Genera `dist/` (estático) — no está commiteado, se genera en cada deploy.
