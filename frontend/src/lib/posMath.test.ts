import { describe, expect, it } from 'vitest';
import { cartSubtotalPaise, lineTotalPaise, orderDiscountPaise, rupeesToPaise, splitFirstPaise } from './posMath';

describe('lineTotalPaise', () => {
  it('multiplies qty by unit price and rounds to integer paise', () => {
    expect(lineTotalPaise(2, 3500)).toBe(7000);
    expect(lineTotalPaise(3, 199)).toBe(597);
  });
});

describe('cartSubtotalPaise', () => {
  it('sums line totals', () => {
    expect(cartSubtotalPaise([
      { qty: 1, unit_price_paise: 3500 },
      { qty: 2, unit_price_paise: 500 },
    ])).toBe(4500);
  });
  it('is zero for an empty cart', () => {
    expect(cartSubtotalPaise([])).toBe(0);
  });
});

describe('orderDiscountPaise', () => {
  it('computes a fixed rupee discount in paise', () => {
    expect(orderDiscountPaise(4000, 'amount', 10)).toBe(1000);
  });
  it('computes a percentage discount', () => {
    expect(orderDiscountPaise(4000, 'percent', 10)).toBe(400);
  });
  it('never exceeds the subtotal', () => {
    expect(orderDiscountPaise(4000, 'amount', 100)).toBe(4000);
    expect(orderDiscountPaise(4000, 'percent', 150)).toBe(4000);
  });
  it('clamps negative input to zero', () => {
    expect(orderDiscountPaise(4000, 'amount', -5)).toBe(0);
  });
});

describe('rupeesToPaise', () => {
  it('converts rupees to integer paise without float drift', () => {
    expect(rupeesToPaise(40)).toBe(4000);
    expect(rupeesToPaise(0.1)).toBe(10);
    expect(rupeesToPaise(19.99)).toBe(1999);
  });
});

describe('splitFirstPaise', () => {
  it('splits the bill into two tenders', () => {
    expect(splitFirstPaise(4000, 1500)).toBe(2500);
  });
  it('never goes negative', () => {
    expect(splitFirstPaise(4000, 5000)).toBe(0);
  });
});
