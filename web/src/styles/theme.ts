export const theme = {
  // Base colors
  background: '#0a0a0f',
  surface: '#12121a',
  surfaceDark: '#0f0f18',
  surfaceLight: '#1a1a24',

  // Primary (Bloomberg amber)
  primary: '#ffaa00',
  primaryDim: '#cc8800',
  primaryBright: '#ffcc44',

  // Semantic colors
  positive: '#00ff88',
  positiveDim: '#00cc6a',
  negative: '#ff3366',
  negativeDim: '#cc2952',
  neutral: '#00d4ff',
  neutralDim: '#00a8cc',
  warning: '#ffaa00',

  // Text colors
  text: '#ffffff',
  textSecondary: '#b0b0b8',
  textDim: '#6a6a7a',
  textMuted: '#4a4a5a',

  // Border colors
  border: '#2a2a3a',
  borderFocus: '#00ff88',
  borderDim: '#1a1a2a',
} as const;

export type Theme = typeof theme;
