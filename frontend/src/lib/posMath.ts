/** Pure counter cart math (integer paise). Extracted for unit testing. */

export function lineTotalPaise(qty: number, unitPricePaise: number): number {
  return Math.round(qty * unitPricePaise);
}

export function cartSubtotalPaise(lines: Array<{ qty: number; unit_price_paise: number }>): number {
  return lines.reduce((sum, line) => sum + lineTotalPaise(line.qty, line.unit_price_paise), 0);
}

export function orderDiscountPaise(subtotalPaise: number, mode: 'amount' | 'percent', value: number): number {
  const v = Math.max(0, value || 0);
  const raw = mode === 'amount'
    ? Math.round(v * 100)
    : Math.round(subtotalPaise * Math.min(100, v) / 100);
  return Math.min(raw, subtotalPaise);
}

export function rupeesToPaise(rupees: number): number {
  return Math.round((rupees || 0) * 100);
}

export function splitFirstPaise(totalPaise: number, secondPaise: number): number {
  return Math.max(0, totalPaise - secondPaise);
}
