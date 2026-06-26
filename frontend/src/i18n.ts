/**
 * Setup react-i18next para Zenic-Flujo frontend.
 *
 * Carga los 3 locales soportados (es, en, pt_br) desde un bundle estático
 * embebido. Originalmente el comentario decía que también se cargaban vía
 * endpoint REST desde el backend (src/core/i18n/locales/*.py), pero esa
 * carga nunca se implementó en este archivo — los recursos se registran
 * estáticamente con `resources: { es: { translation: es }, ... }`.
 *
 * P2-11 (zenic-3a): se removieron las claves muertas (sin callers en
 * frontend/src). El bundle ahora contiene solo las 19 claves realmente
 * usadas por MiNegocioPage.tsx (12 estáticas + 7 dinámicas
 * `crm.stage_${stage}`). Si se migran más páginas a t(), re-añadir las
 * claves que se necesiten.
 *
 * BUG-31 (frontend-bugs.md): "No i18n en frontend" — resuelto por este archivo.
 */
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

// Bundle estático embebido para arranque offline y SSR.
// P2-11: solo claves con callers reales en frontend/src.
import es from './locales/es.json';
import en from './locales/en.json';
import pt_br from './locales/pt_br.json';

export const SUPPORTED_LANGUAGES = ['es', 'en', 'pt_br'] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];
export const DEFAULT_LANGUAGE: SupportedLanguage = 'es';

function detectInitialLanguage(): SupportedLanguage {
  if (typeof window === 'undefined') return DEFAULT_LANGUAGE;
  const stored = window.localStorage?.getItem('zenic.lang');
  if (stored && (SUPPORTED_LANGUAGES as readonly string[]).includes(stored)) {
    return stored as SupportedLanguage;
  }
  const nav = window.navigator?.language?.toLowerCase() ?? '';
  if (nav.startsWith('pt')) return 'pt_br';
  if (nav.startsWith('en')) return 'en';
  return DEFAULT_LANGUAGE;
}

i18n.use(initReactI18next).init({
  resources: {
    es: { translation: es },
    en: { translation: en },
    pt_br: { translation: pt_br },
  },
  lng: detectInitialLanguage(),
  fallbackLng: DEFAULT_LANGUAGE,
  interpolation: {
    // React ya escapa valores por defecto, no necesitamos doble escape.
    escapeValue: false,
  },
  returnEmptyString: false,
  parseMissingKeyHandler: (key: string) => {
    if (import.meta.env.DEV) {
      // En dev, alerta visual de claves faltantes para acelerar la migración.
      console.warn(`[i18n] clave faltante: ${key}`);
    }
    return key;
  },
});

/**
 * Cambia el idioma activo y lo persiste en localStorage.
 * Si la página ya está cargada, react-i18next re-renderiza automáticamente.
 */
export async function changeLanguage(lang: SupportedLanguage): Promise<void> {
  await i18n.changeLanguage(lang);
  if (typeof window !== 'undefined') {
    window.localStorage?.setItem('zenic.lang', lang);
    document.documentElement.lang = lang === 'pt_br' ? 'pt-BR' : lang;
  }
}

export default i18n;
