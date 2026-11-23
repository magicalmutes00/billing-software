import { useCallback, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pause, Play, Plus, Printer, Search, Share2, X, XCircle } from 'lucide-react';
import { apiErrorMessage, apiGet, apiSend, printAuthenticatedHtml } from '../lib/api';
import { inr } from '../lib/format';
import { cartSubtotalPaise, orderDiscountPaise } from '../lib/posMath';
import { Badge, Button, Card, CardHeader, Field, Input, Modal, PageHeader, Skeleton, useToast } from '../components/ui';
import { UpiQr } from '../components/UpiQr';
import { useAuth } from '../context/AuthContext';
import type { HeldOrder, MenuCategory, MenuProduct, ModifierGroup, PosPayment, PosSale } from '../types';

type CartLine = {
  product_id: string;
  product_name: string;
  variant_id: string | null;
  variant_name: string | null;
  modifier_ids: string[];
  modifiers: { id: string; name: string; price_paise: number }[];
  qty: number;
  unit_price_paise: number;
};

function tileStyle(color: string | undefined | null) {
  return { background: color || '#3538cd', color: '#ffffff' };
}

function initials(name: string) {
  return name.split(/\s+/).map((part) => part[0]).slice(0, 2).join('').toUpperCase();
}

export default function Pos() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const { user } = useAuth();
  const shopName = user?.tenant_name || 'Your shop';

  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  const menu = useQuery({
    queryKey: ['pos', 'menu'],
    queryFn: async () => (await apiGet<MenuCategory[]>('/pos/menu')).data,
  });

  // ---------- Held / parked orders ----------
  const holds = useQuery({
    queryKey: ['pos', 'holds'],
    queryFn: async () => (await apiGet<HeldOrder[]>('/pos/holds')).data,
  });
  const [holdLabel, setHoldLabel] = useState('');
  const holdCart = useMutation({
    mutationFn: async () => (await apiSend<HeldOrder>('post', '/pos/holds', {
      label: holdLabel || null,
      cart: { lines: cart, discountValue, discountMode },
    })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pos', 'holds'] });
      setCart([]); setDiscountValue(''); setHoldLabel('');
      notify('Order held', 'success');
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });
  const resumeHold = useMutation({
    mutationFn: async (id: string) => (await apiSend<{ lines: CartLine[]; discountValue: string; discountMode: 'amount' | 'percent' }>('post', `/pos/holds/${id}/resume`)).data,
    onSuccess: (held) => {
      queryClient.invalidateQueries({ queryKey: ['pos', 'holds'] });
      setCart(held.lines || []);
      setDiscountValue(held.discountValue || '');
      setDiscountMode(held.discountMode || 'amount');
      setSaleId(null);
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });
  const dropHold = useMutation({
    mutationFn: async (id: string) => (await apiSend('delete', `/pos/holds/${id}`)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['pos', 'holds'] }),
  });

  // ---------- Cart ----------
  const [cart, setCart] = useState<CartLine[]>([]);
  const [discountMode, setDiscountMode] = useState<'amount' | 'percent'>('amount');
  const [discountValue, setDiscountValue] = useState('');

  const addToCart = useCallback((product: MenuProduct, variant: MenuProduct['variants'][number] | null, modifierIds: string[], qty: number) => {
    const modifierMap = new Map<string, { id: string; name: string; price_paise: number }>();
    product.modifier_groups.forEach((group) => group.modifiers.forEach((m) => modifierMap.set(m.id, m)));
    const modifiers = modifierIds.filter((id) => modifierMap.has(id)).map((id) => modifierMap.get(id)!);
    const unitPrice = (variant ? variant.price_paise : product.base_price_paise) + modifiers.reduce((sum, m) => sum + m.price_paise, 0);
    const sortedModifiers = modifierIds.slice().sort();
    setCart((current) => {
      const existing = current.findIndex(
        (line) => line.product_id === product.id && line.variant_id === (variant?.id ?? null)
          && JSON.stringify(line.modifier_ids.slice().sort()) === JSON.stringify(sortedModifiers),
      );
      if (existing >= 0) {
        return current.map((line, i) => (i === existing ? { ...line, qty: line.qty + qty } : line));
      }
      return [...current, {
        product_id: product.id, product_name: product.name,
        variant_id: variant?.id ?? null, variant_name: variant?.name ?? null,
        modifier_ids: modifierIds, modifiers, qty, unit_price_paise: unitPrice,
      }];
    });
  }, []);

  const setQty = useCallback((index: number, qty: number) => {
    if (qty <= 0) {
      setCart((current) => current.filter((_, i) => i !== index));
      return;
    }
    setCart((current) => current.map((line, i) => (i === index ? { ...line, qty } : line)));
  }, []);

  const removeLine = useCallback((index: number) => {
    setCart((current) => current.filter((_, i) => i !== index));
  }, []);

  const subtotalPaise = cartSubtotalPaise(cart);
  const discountPaise = orderDiscountPaise(subtotalPaise, discountMode, Number(discountValue || 0));
  const totalPaise = subtotalPaise - discountPaise;

  // ---------- Product picker ----------
  const [openProduct, setOpenProduct] = useState<MenuProduct | null>(null);
  const [selectedVariantId, setSelectedVariantId] = useState<string | null>(null);
  const [selectedModifierIds, setSelectedModifierIds] = useState<string[]>([]);
  const [pickerQty, setPickerQty] = useState(1);

  function openPicker(product: MenuProduct) {
    setOpenProduct(product);
    const defaults = product.variants.find((v) => v.is_default) ?? product.variants[0];
    setSelectedVariantId(defaults ? defaults.id : null);
    setSelectedModifierIds([]);
    setPickerQty(1);
  }

  function toggleModifier(group: ModifierGroup, id: string) {
    setSelectedModifierIds((current) => {
      const next = current.includes(id) ? current.filter((x) => x !== id) : [...current, id];
      const max = group.max_select || 1;
      return next.length > max ? next.slice(next.length - max) : next;
    });
  }

  function pickerUnitPaise() {
    if (!openProduct) return 0;
    const variantPrice = openProduct.variants.find((v) => v.id === selectedVariantId)?.price_paise ?? openProduct.base_price_paise;
    const addonPrice = openProduct.modifier_groups.reduce(
      (sum, group) => sum + group.modifiers.filter((m) => selectedModifierIds.includes(m.id)).reduce((s, m) => s + m.price_paise, 0),
      0,
    );
    return variantPrice + addonPrice;
  }

  // ---------- Payment ----------
  const [payOpen, setPayOpen] = useState(false);
  const [method, setMethod] = useState<'CASH' | 'UPI' | 'CARD'>('CASH');
  const [tendered, setTendered] = useState('');
  const [reference, setReference] = useState('');
  const [splitMode, setSplitMode] = useState(false);
  const [splitMethod, setSplitMethod] = useState<'CASH' | 'UPI' | 'CARD'>('UPI');
  const [splitAmount, setSplitAmount] = useState('');

  const createSale = useMutation({
    mutationFn: async () => {
      const items = cart.map((line) => ({
        product_id: line.product_id,
        variant_id: line.variant_id,
        modifier_ids: line.modifier_ids,
        qty: line.qty,
      }));
      let payload: Record<string, unknown>;
      if (splitMode) {
        const secondPaise = Math.round(Number(splitAmount || 0) * 100);
        const firstPaise = totalPaise - secondPaise;
        const payments: PosPayment[] = [
          { method, amount_paise: firstPaise, tendered_paise: method === 'CASH' ? Math.round(Number(tendered || 0) * 100) : firstPaise, reference_no: reference || null },
          { method: splitMethod, amount_paise: secondPaise, tendered_paise: splitMethod === 'CASH' ? secondPaise : secondPaise, reference_no: null },
        ];
        payload = { items, discount_paise: discountPaise, payments };
      } else {
        const payment: PosPayment = {
          method,
          tendered_paise: method === 'CASH' ? Math.round(Number(tendered || 0) * 100) : null,
          reference_no: reference || null,
        };
        payload = { items, discount_paise: discountPaise, payment };
      }
      return (await apiSend<PosSale>('post', '/pos/sales', payload)).data;
    },
    onSuccess: (sale) => {
      queryClient.invalidateQueries({ queryKey: ['pos', 'menu'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['pos', 'sales'] });
      setPayOpen(false);
      setCart([]);
      setDiscountValue('');
      setTendered('');
      setReference('');
      setSplitMode(false);
      setSplitAmount('');
      setSaleId(sale.id);
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  // ---------- Recent sale ----------
  const [saleId, setSaleId] = useState<string | null>(null);
  const shareReceipt = useMutation({
    mutationFn: async (id: string) => (await apiSend<{ token: string }>('post', `/pos/sales/${id}/share-token`)).data,
    onSuccess: ({ token }) => {
      const url = `${window.location.origin}/api/v1/public/receipt/${token}`;
      const wa = `https://wa.me/?text=${encodeURIComponent(`Here is your receipt: ${url}`)}`;
      window.open(wa, '_blank');
      void navigator.clipboard?.writeText(url).catch(() => {});
      notify('Receipt link copied — opening WhatsApp', 'success');
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });
  const sale = useQuery({
    queryKey: ['pos', 'sale', saleId],
    queryFn: async () => (await apiGet<PosSale>(`/pos/sales/${saleId!}`)).data,
    enabled: !!saleId,
  });

  function startNewSale() {
    setSaleId(null);
    setCart([]);
    setDiscountValue('');
    setSearch('');
    setActiveCategory(null);
  }

  if (menu.isLoading) return <Skeleton rows={8} />;
  if (menu.isError) return <div className="text-sm text-rose-600">{apiErrorMessage(menu.error)}</div>;
  const categories = menu.data || [];

  return (
    <div className="space-y-6">
      {saleId && sale.data ? (
        <div>
          <PageHeader title={`Bill ${sale.data.number || '—'}`} subtitle="Counter sale completed" actions={<Button variant="primary" onClick={startNewSale}><Plus size={15} /> New sale</Button>} />
          <div className="grid gap-5 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader title="Receipt preview" subtitle={`Paid by ${sale.data.pos_meta?.method || '—'}`} />
              <div className="p-5">
                <div className="mx-auto max-w-xs rounded-xl border border-line bg-white p-5 shadow-sm">
                  <div className="text-center text-sm font-bold uppercase tracking-wide text-ink">{shopName}</div>
                  <div className="mt-2 text-xs font-medium text-ink">{sale.data.number || '—'}</div>
                  <div className="text-[11px] text-muted">{new Date(sale.data.created_at || sale.data.issue_date).toLocaleString('en-IN')}</div>
                  {sale.data.pos_meta?.cashier && <div className="text-[11px] text-muted">Cashier: {sale.data.pos_meta.cashier}</div>}
                  <hr className="my-3 border-dashed" />
                  <div className="space-y-2">
                    {sale.data.items.map((item, i) => (
                      <div key={i}>
                        <div className="text-xs text-ink">{item.description}</div>
                        <div className="flex justify-between text-[11px] text-muted">
                          <span>{item.qty} × {inr(item.unit_price_paise)}</span>
                          <span>{inr(item.total_paise)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                  <hr className="my-3 border-dashed" />
                  <div className="flex justify-between text-sm font-semibold text-ink"><span>TOTAL</span><span>{inr(sale.data.total_paise)}</span></div>
                  {sale.data.pos_meta?.tendered_paise != null && (
                    <div className="flex justify-between text-[11px] text-muted"><span>Tendered</span><span>{inr(sale.data.pos_meta.tendered_paise)}</span></div>
                  )}
                  {sale.data.pos_meta?.change_paise != null && (
                    <div className="flex justify-between text-[11px] text-muted"><span>Change</span><span>{inr(sale.data.pos_meta.change_paise)}</span></div>
                  )}
                  <hr className="my-3 border-dashed" />
                  <div className="text-center text-[11px] text-muted">Thank you! Visit again.</div>
                </div>
                <div className="mt-4 flex justify-center gap-2">
                  <Button variant="primary" onClick={() => { void printAuthenticatedHtml(`/api/v1/pos/sales/${sale.data!.id}/receipt`); }}><Printer size={15} /> Print 80 mm receipt</Button>
                  <Button onClick={() => shareReceipt.mutate(sale.data!.id)} loading={shareReceipt.isPending}><Share2 size={15} /> Share receipt</Button>
                </div>
              </div>
            </Card>
            <Card>
              <CardHeader title="Sale summary" />
              <div className="space-y-3 p-5 text-sm">
                <div className="flex justify-between"><span className="text-muted">Subtotal</span><span>{inr(sale.data.subtotal_paise)}</span></div>
                <div className="flex justify-between"><span className="text-muted">Discount</span><span className="text-rose-600">-{inr(sale.data.discount_paise)}</span></div>
                <div className="flex justify-between"><span className="text-muted">Payment</span><span>{sale.data.pos_meta?.method || '—'}</span></div>
                <div className="flex justify-between border-t border-line pt-2 font-semibold"><span>Total</span><span>{inr(sale.data.total_paise)}</span></div>
              </div>
            </Card>
          </div>
        </div>
      ) : (
        <>
          <PageHeader
            title="Counter"
            subtitle="Tap a product, review the cart, take payment and print a receipt."
            actions={<Button onClick={startNewSale}><X size={15} /> Clear cart</Button>}
          />
          <div className="grid gap-6 lg:grid-cols-12">
            {/* Menu */}
            <div className="lg:col-span-7">
              <Card>
                <div className="p-4">
                  <div className="relative mb-3">
                    <Search size={15} className="absolute left-3 top-2.5 text-muted" />
                    <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search products…" className="pl-9" />
                  </div>
                  <div className="mb-4 flex flex-wrap gap-2">
                    <button onClick={() => setActiveCategory(null)} className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${activeCategory === null ? 'bg-brand-600 text-white' : 'bg-white text-muted ring-1 ring-line hover:text-ink'}`}>All</button>
                    {categories.map((category) => (
                      <button key={category.id} onClick={() => setActiveCategory(category.id)} className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${activeCategory === category.id ? 'bg-brand-600 text-white' : 'bg-white text-muted ring-1 ring-line hover:text-ink'}`}>
                        {category.name}
                      </button>
                    ))}
                  </div>
                  {categories.length === 0 && <div className="py-12 text-center text-sm text-muted">No products yet. Add them in Catalog.</div>}
                  <div className="space-y-4">
                    {categories
                      .filter((category) => activeCategory === null || category.id === activeCategory)
                      .map((category) => {
                        const products = (category.products || []).filter((p) =>
                          p.name.toLowerCase().includes(search.toLowerCase()) ||
                          (p.description || '').toLowerCase().includes(search.toLowerCase()),
                        );
                        if (products.length === 0) return null;
                        return (
                          <div key={category.id}>
                            <div className="mb-2 flex items-center gap-2">
                              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">{category.name}</h2>
                              <Badge tone="bg-slate-100 text-slate-600 ring-slate-200">{products.length}</Badge>
                            </div>
                            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                              {products.map((product) => (
                                <button
                                  key={product.id}
                                  onClick={() => openPicker(product)}
                                  className="flex flex-col items-center gap-2 rounded-xl border border-line bg-white p-3 text-center transition hover:border-brand-300 hover:bg-brand-50/50 active:scale-[0.98]"
                                >
                                  <div className="grid h-11 w-11 place-items-center rounded-lg text-xs font-bold shadow-sm" style={tileStyle(category.color)}>{initials(product.name)}</div>
                                  <div className="w-full">
                                    <div className="truncate text-sm font-medium text-ink">{product.name}</div>
                                    <div className="text-xs text-muted">{inr(product.variants.find((v) => v.is_default)?.price_paise ?? product.base_price_paise)}</div>
                                    {product.variants.length > 1 && <div className="text-[10px] text-muted">{product.variants.map((v) => v.name).join(' · ')}</div>}
                                    {product.modifier_groups.length > 0 && <div className="text-[10px] font-semibold text-brand-600">+ add-ons</div>}
                                  </div>
                                </button>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    {search && categories.every((c) => !(c.products || []).some((p) => p.name.toLowerCase().includes(search.toLowerCase()))) && (
                      <div className="py-8 text-center text-sm text-muted">No products match “{search}”.</div>
                    )}
                  </div>
                </div>
              </Card>
            </div>

            {/* Cart */}
            <div className="lg:col-span-5">
              <Card>
                <CardHeader title={`Cart (${cart.length})`} subtitle={cart.length === 0 ? 'Add items from the menu' : 'Review before payment'} />
                {cart.length === 0 ? (
                  <div className="py-14 text-center text-sm text-muted">Your cart is empty.</div>
                ) : (
                  <>
                    <div className="max-h-[45vh] space-y-3 overflow-y-auto p-4">
                      {cart.map((line, index) => (
                        <div key={index} className="rounded-lg border border-line p-3">
                          <div className="flex justify-between gap-2">
                            <span className="truncate text-sm font-medium text-ink">{line.product_name}</span>
                            <span className="text-sm font-medium text-ink">{inr(Math.round(line.qty * line.unit_price_paise))}</span>
                          </div>
                          {(line.variant_name || line.modifiers.length > 0) && (
                            <div className="mt-0.5 text-[11px] text-muted">
                              {[line.variant_name, ...line.modifiers.map((m) => m.name)].filter(Boolean).join(' · ')}
                            </div>
                          )}
                          <div className="mt-2 flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <button onClick={() => setQty(index, line.qty - 1)} className="grid h-7 w-7 place-items-center rounded-md border border-line text-sm text-muted hover:bg-slate-50">−</button>
                              <span className="w-5 text-center text-xs font-semibold text-ink">{line.qty}</span>
                              <button onClick={() => setQty(index, line.qty + 1)} className="grid h-7 w-7 place-items-center rounded-md border border-line text-sm text-muted hover:bg-slate-50">+</button>
                            </div>
                            <button onClick={() => removeLine(index)} className="rounded-md p-1 text-rose-600 hover:bg-rose-50" title="Remove"><XCircle size={15} /></button>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="space-y-2 border-t border-line p-4 text-sm">
                      <div className="flex justify-between"><span className="text-muted">Subtotal</span><span>{inr(subtotalPaise)}</span></div>
                      <div className="flex flex-wrap items-center gap-2">
                        <select value={discountMode} onChange={(e) => setDiscountMode(e.target.value as 'amount' | 'percent')} className="rounded-md border border-line bg-white px-2 py-1.5 text-xs">
                          <option value="amount">₹ Discount</option>
                          <option value="percent">% Discount</option>
                        </select>
                        <Input type="number" step="0.01" min="0" value={discountValue} onChange={(e) => setDiscountValue(e.target.value)} placeholder="0.00" className="w-24 text-right text-xs" />
                        <span className="ml-auto font-medium text-rose-600">-{inr(discountPaise)}</span>
                      </div>
                      <div className="flex justify-between border-t border-line pt-2 text-base font-semibold"><span>Total</span><span>{inr(totalPaise)}</span></div>
                    </div>
                  </>
                )}
                <div className="border-t border-line p-4">
                  <div className="flex gap-2">
                    <Button variant="primary" className="flex-1" disabled={cart.length === 0 || totalPaise <= 0 || createSale.isPending} loading={createSale.isPending} onClick={() => {
                      setTendered((totalPaise / 100).toFixed(2));
                      setMethod('CASH');
                      setSplitMode(false);
                      setPayOpen(true);
                    }}>Checkout · {inr(totalPaise)}</Button>
                    <Button disabled={cart.length === 0 || holdCart.isPending} loading={holdCart.isPending} onClick={() => holdCart.mutate()} title="Hold this order"><Pause size={15} /> Hold</Button>
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-1">
                    {[500, 1000, 2000, 5000, 10000, 50000].map((paise) => (
                      <button key={paise} onClick={() => setTendered((paise / 100).toFixed(2))} className="rounded-md border border-line bg-white px-1 py-1.5 text-xs text-muted hover:bg-brand-50 hover:text-brand-600">₹{paise / 100}</button>
                    ))}
                  </div>
                  {(holds.data?.length ?? 0) > 0 && (
                    <div className="mt-4 border-t border-line pt-3">
                      <div className="mb-2 text-xs font-semibold text-muted">Held orders ({holds.data!.length})</div>
                      <div className="space-y-1">
                        {holds.data!.map((hold) => (
                          <div key={hold.id} className="flex items-center justify-between rounded-md border border-line px-2 py-1.5 text-xs">
                            <span className="truncate text-ink">{hold.label || 'Held order'}</span>
                            <span className="flex items-center gap-1">
                              <button onClick={() => resumeHold.mutate(hold.id)} className="rounded p-1 text-brand-600 hover:bg-brand-50" title="Resume"><Play size={13} /></button>
                              <button onClick={() => dropHold.mutate(hold.id)} className="rounded p-1 text-rose-600 hover:bg-rose-50" title="Discard"><X size={13} /></button>
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </Card>
            </div>
          </div>

          {/* Product picker */}
          {openProduct && (
            <Modal open onClose={() => setOpenProduct(null)} title={openProduct.name} width="max-w-lg">
              <form onSubmit={(e) => { e.preventDefault(); addToCart(openProduct, openProduct.variants.find((v) => v.id === selectedVariantId) ?? null, selectedModifierIds, pickerQty); setOpenProduct(null); }} className="space-y-5">
                {openProduct.variants.length > 1 && (
                  <div>
                    <div className="mb-2 text-xs font-semibold text-muted">Choose size</div>
                    <div className="grid grid-cols-3 gap-2">
                      {openProduct.variants.map((variant) => (
                        <button key={variant.id} type="button" onClick={() => setSelectedVariantId(variant.id)} className={`rounded-lg border px-2 py-2 text-xs font-medium transition ${selectedVariantId === variant.id ? 'border-brand-600 bg-brand-600 text-white' : 'border-line bg-white text-ink hover:bg-slate-50'}`}>
                          {variant.name}<br />{inr(variant.price_paise)}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {openProduct.modifier_groups.map((group) => (
                  <div key={group.id}>
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-xs font-semibold text-muted">{group.name}{group.is_required ? <span className="ml-1 text-rose-600">*</span> : null}</span>
                      <span className="text-[11px] text-muted">{group.modifiers.filter((m) => selectedModifierIds.includes(m.id)).length}/{group.max_select}</span>
                    </div>
                    <div className="grid gap-1 sm:grid-cols-2">
                      {group.modifiers.map((modifier) => {
                        const selected = selectedModifierIds.includes(modifier.id);
                        return (
                          <button key={modifier.id} type="button" onClick={() => toggleModifier(group, modifier.id)} className={`flex items-center justify-between rounded-lg border px-3 py-2 text-xs transition ${selected ? 'border-brand-300 bg-brand-50 text-brand-700' : 'border-line bg-white text-ink hover:bg-slate-50'}`}>
                            <span>{modifier.name}</span>
                            <span className={selected ? 'font-semibold' : 'text-muted'}>{modifier.price_paise > 0 ? `+${inr(modifier.price_paise)}` : selected ? '✓' : ''}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
                <div className="flex items-end justify-between gap-3 border-t border-line pt-4">
                  <div>
                    <div className="mb-1 text-[11px] text-muted">Qty</div>
                    <Input type="number" min="1" value={pickerQty} onChange={(e) => setPickerQty(Math.max(1, Number(e.target.value || 1)))} className="w-20" />
                  </div>
                  <div className="text-right">
                    <div className="text-[11px] text-muted">Line total</div>
                    <div className="text-sm font-semibold text-ink">{inr(pickerUnitPaise() * pickerQty)}</div>
                  </div>
                  <Button type="submit" variant="primary">Add to cart</Button>
                </div>
              </form>
            </Modal>
          )}

          {/* Payment */}
          <Modal open={payOpen} onClose={() => setPayOpen(false)} title="Take payment" width="max-w-md">
            <form onSubmit={(e) => { e.preventDefault(); createSale.mutate(); }} className="space-y-4">
              <div className="rounded-lg bg-slate-50 p-3 text-right">
                <div className="text-[11px] text-muted">Amount due</div>
                <div className="text-2xl font-semibold text-ink">{inr(totalPaise)}</div>
              </div>
              <Field label="Payment method">
                <div className="grid grid-cols-3 gap-2">
                  {(['CASH', 'UPI', 'CARD'] as const).map((option) => (
                    <button key={option} type="button" onClick={() => { setMethod(option); setTendered(option === 'CASH' ? (totalPaise / 100).toFixed(2) : ''); }} className={`rounded-lg border px-3 py-2 text-sm font-medium transition ${method === option ? 'border-brand-600 bg-brand-600 text-white' : 'border-line bg-white text-ink hover:bg-slate-50'}`}>
                      {option === 'CASH' ? 'Cash' : option}
                    </button>
                  ))}
                </div>
              </Field>
              {method === 'UPI' && !splitMode && (
                <div className="rounded-lg border border-line bg-white p-3"><UpiQr amountPaise={totalPaise} /></div>
              )}
              {method === 'CASH' ? (
                <>
                  <Field label={splitMode ? 'Cash tendered (₹)' : 'Tendered (₹)'}><Input type="number" step="0.01" min="0" value={tendered} onChange={(e) => setTendered(e.target.value)} required /></Field>
                  <div className="flex justify-between text-sm font-medium"><span className="text-muted">Change due</span><span className="text-brand-600">{inr(Math.max(0, Math.round(Number(tendered || 0) * 100) - (splitMode ? totalPaise - Math.round(Number(splitAmount || 0) * 100) : totalPaise)))}</span></div>
                </>
              ) : (
                <Field label="Reference no. (optional)"><Input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="UPI txn / card slip no." /></Field>
              )}
              <label className="flex items-center gap-2 text-xs text-muted">
                <input type="checkbox" checked={splitMode} onChange={(e) => { setSplitMode(e.target.checked); if (e.target.checked) setSplitAmount((totalPaise / 200).toFixed(2)); }} />
                Split payment across two methods
              </label>
              {splitMode && (
                <div className="space-y-2 rounded-lg bg-slate-50 p-3">
                  <div className="flex justify-between text-xs"><span className="text-muted">First ({method})</span><span className="font-medium text-ink">{inr(Math.max(0, totalPaise - Math.round(Number(splitAmount || 0) * 100)))}</span></div>
                  <div className="flex items-end gap-2">
                    <Field label="Second method">
                      <select value={splitMethod} onChange={(e) => setSplitMethod(e.target.value as 'CASH' | 'UPI' | 'CARD')} className="rounded-md border border-line bg-white px-2 py-1.5 text-xs">
                        <option value="UPI">UPI</option><option value="CASH">Cash</option><option value="CARD">Card</option>
                      </select>
                    </Field>
                    <Field label="Second amount (₹)"><Input type="number" step="0.01" min="0" value={splitAmount} onChange={(e) => setSplitAmount(e.target.value)} className="w-28 text-right" /></Field>
                  </div>
                </div>
              )}
              <div className="flex justify-end gap-2 border-t border-line pt-4">
                <Button type="button" onClick={() => setPayOpen(false)}>Cancel</Button>
                <Button type="submit" variant="primary" loading={createSale.isPending} disabled={createSale.isPending || (splitMode
                  ? (Math.round(Number(splitAmount || 0) * 100) <= 0 || Math.round(Number(splitAmount || 0) * 100) >= totalPaise || (method === 'CASH' && Math.round(Number(tendered || 0) * 100) < totalPaise - Math.round(Number(splitAmount || 0) * 100)))
                  : (method === 'CASH' && Math.round(Number(tendered || 0) * 100) < totalPaise))}>Confirm payment</Button>
              </div>
            </form>
          </Modal>
        </>
      )}
    </div>
  );
}
