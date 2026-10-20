export function listedLogoUrl(symbol: string, _exchange = "NSE") {
  const file = encodeURIComponent(symbol.trim().toUpperCase().replace(/-/g, "_"));
  return `https://api.dharun.dev/v1/logos/${file}`;
}
