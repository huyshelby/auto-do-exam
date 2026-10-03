/**
 * Thuật toán tính độ trễ sinh học người dùng theo phân phối Gauss (Box-Muller Transform)
 */

export function randomGaussian(mean = 0, std = 1) {
  let u = 0, v = 0;
  while (u === 0) u = Math.random(); // Tránh log(0)
  while (v === 0) v = Math.random();
  const z = Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
  return z * std + mean;
}

export function calculateHumanDelay(text, config) {
  const words = text.trim().split(/\s+/);
  const nWords = Math.max(5, words.length);

  const vRead = Math.max(2.0, randomGaussian(config.WORDS_PER_SEC_MEAN, config.WORDS_PER_SEC_STD));
  const tReadMs = (nWords / vRead) * 1000;

  const tDecisionMs = Math.max(600, randomGaussian(config.DECISION_TIME_MEAN_MS, config.DECISION_TIME_STD_MS));
  const tJitterMs = (Math.random() * 500) - 200; // -200ms đến +300ms

  const total = Math.round(tReadMs + tDecisionMs + tJitterMs);
  return Math.max(config.MIN_DELAY_MS, Math.min(total, config.MAX_DELAY_MS));
}

export const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
