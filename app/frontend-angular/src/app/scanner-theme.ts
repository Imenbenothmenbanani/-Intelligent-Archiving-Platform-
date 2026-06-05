import { definePreset } from '@primeng/themes';
import Aura from '@primeng/themes/aura';

export const ScannerTheme = definePreset(Aura, {
  primitive: {
    borderRadius: {
      sm: '8px',
      md: '14px',
      lg: '18px',
      xl: '24px'
    }
  },
  semantic: {
    primary: {
      50: '#eef6ff',
      100: '#d9e9ff',
      200: '#b8d4ff',
      300: '#88b8ff',
      400: '#5699f2',
      500: '#2878d8',
      600: '#0f5fbf',
      700: '#0a4d9b',
      800: '#083f7d',
      900: '#07315f',
      950: '#041c3a'
    },
    colorScheme: {
      light: {
        surface: {
          0: '#ffffff',
          50: '#f7f9fc',
          100: '#edf2f8',
          200: '#d9e1eb',
          300: '#bcc9d8',
          400: '#93a6bc',
          500: '#6f849c',
          600: '#576d87',
          700: '#44566f',
          800: '#2f4258',
          900: '#1d3043',
          950: '#0a1828'
        }
      }
    }
  }
});
