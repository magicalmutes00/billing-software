import { useCallback, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2, X } from 'lucide-react';
import { apiErrorMessage, apiGet, apiSend } from '../lib/api';
import { inr } from '../lib/format';
import { Badge, Button, Card, CardHeader, DataTable, Field, Input, Modal, PageHeader, Skeleton, Tab, Tabs, useToast, type Column } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import type { Category, ModifierGroup, Product, Variant } from '../types';

function emptyVariant(): Variant {
  return { id: '', name: '', price_paise: 0, is_default: false, sort_order: 0, is_active: true };
}

export default function Catalog() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const { can } = useAuth();
  const [activeTab, setActiveTab] = useState<'products' | 'categories' | 'addons'>('products');

  // ---------- Categories ----------
  const categories = useQuery({
    queryKey: ['catalog', 'categories'],
    queryFn: async () => (await apiGet<Category[]>('/catalog/categories')).data,
  });
  const [catOpen, setCatOpen] = useState(false);
  const [catName, setCatName] = useState('');
  const [catColor, setCatColor] = useState('#3538cd');
  const [catSort, setCatSort] = useState('0');
  const createCategory = useMutation({
    mutationFn: async () => (await apiSend('post', '/catalog/categories', {
      name: catName, color: catColor, sort_order: Number(catSort || 0), is_active: true,
    })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalog', 'categories'] });
      queryClient.invalidateQueries({ queryKey: ['catalog', 'products'] });
      setCatOpen(false); setCatName(''); setCatSort('0');
      notify('Category created');
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });
  const deactivateCategory = useMutation({
    mutationFn: async (id: string) => (await apiSend('delete', `/catalog/categories/${id}`)).data,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['catalog', 'categories'] }); notify('Category deactivated'); },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  // ---------- Add-on groups ----------
  const addons = useQuery({
    queryKey: ['catalog', 'addons'],
    queryFn: async () => (await apiGet<ModifierGroup[]>('/catalog/modifier-groups')).data,
  });
  const [addonOpen, setAddonOpen] = useState(false);
  const [addonName, setAddonName] = useState('');
  const [addonMin, setAddonMin] = useState('0');
  const [addonMax, setAddonMax] = useState('1');
  const [addonRequired, setAddonRequired] = useState(false);
  const [addonOptions, setAddonOptions] = useState<{ name: string; price_paise: number }[]>([]);
  function addAddonOption() { setAddonOptions([...addonOptions, { name: '', price_paise: 0 }]); }
  function removeAddonOption(i: number) { setAddonOptions(addonOptions.filter((_, idx) => idx !== i)); }
  const createAddon = useMutation({
    mutationFn: async () => (await apiSend('post', '/catalog/modifier-groups', {
      name: addonName, min_select: Number(addonMin || 0), max_select: Number(addonMax || 1),
      is_required: addonRequired, is_active: true,
      modifiers: addonOptions.filter((o) => o.name.trim()).map((o) => ({ name: o.name, price_paise: o.price_paise, sort_order: 0, is_active: true })),
    })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalog', 'addons'] });
      queryClient.invalidateQueries({ queryKey: ['catalog', 'products'] });
      setAddonOpen(false); setAddonName(''); setAddonMin('0'); setAddonMax('1'); setAddonRequired(false); setAddonOptions([]);
      notify('Add-on group created');
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  // ---------- Products ----------
  const products = useQuery({
    queryKey: ['catalog', 'products'],
    queryFn: async () => (await apiGet<Product[]>('/catalog/products')).data,
  });
  const [prodOpen, setProdOpen] = useState(false);
  const [prodCategory, setProdCategory] = useState('');
  const [prodName, setProdName] = useState('');
  const [prodDesc, setProdDesc] = useState('');
  const [prodPrice, setProdPrice] = useState('');
  const [prodTax, setProdTax] = useState('0');
  const [prodHsn, setProdHsn] = useState('');
  const [prodSku, setProdSku] = useState('');
  const [prodBarcode, setProdBarcode] = useState('');
  const [prodVariants, setProdVariants] = useState<Variant[]>([emptyVariant()]);
  const [prodGroupIds, setProdGroupIds] = useState<string[]>([]);
  function addVariant() { setProdVariants([...prodVariants, emptyVariant()]); }
  function removeVariant(i: number) { setProdVariants(prodVariants.filter((_, idx) => idx !== i)); }
  function toggleGroup(id: string) { setProdGroupIds((current) => current.includes(id) ? current.filter((x) => x !== id) : [...current, id]); }
  const createProduct = useMutation({
    mutationFn: async () => {
      const variants = prodVariants.filter((v) => v.name.trim());
      return (await apiSend('post', '/catalog/products', {
        category_id: prodCategory,
        name: prodName,
        description: prodDesc || null,
        base_price_paise: Math.round(Number(prodPrice || 0) * 100),
        tax_rate_pct: Number(prodTax || 0),
        hsn_sac: prodHsn || null,
        sku: prodSku || null,
        barcode: prodBarcode || null,
        variants: variants.map((v, i) => ({ name: v.name, price_paise: v.price_paise, is_default: i === 0, sort_order: i + 1, is_active: true })),
        modifier_group_ids: prodGroupIds,
      })).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalog', 'products'] });
      queryClient.invalidateQueries({ queryKey: ['pos', 'menu'] });
      setProdOpen(false); setProdName(''); setProdDesc(''); setProdPrice(''); setProdTax('0'); setProdHsn(''); setProdSku(''); setProdBarcode(''); setProdVariants([emptyVariant()]); setProdGroupIds([]);
      notify('Product created');
    },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  const deactivateProduct = useMutation({
    mutationFn: async (id: string) => (await apiSend('delete', `/catalog/products/${id}`)).data,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['catalog', 'products'] }); queryClient.invalidateQueries({ queryKey: ['pos', 'menu'] }); notify('Product deactivated'); },
    onError: (err) => notify(apiErrorMessage(err), 'error'),
  });

  if (categories.isLoading || products.isLoading || addons.isLoading) return <Skeleton rows={8} />;
  const catList = categories.data || [];
  const prodList = products.data || [];
  const addonList = addons.data || [];

  const columns: Column<Product>[] = [
    { key: 'name', header: 'Product', render: (row) => <div><div className="font-medium text-ink">{row.name}</div>{row.description && <div className="text-[11px] text-muted">{row.description}</div>}</div> },
    { key: 'category', header: 'Category', render: (row) => <span className="text-xs text-muted">{catList.find((c) => c.id === row.category_id)?.name || '—'}</span> },
    { key: 'price', header: 'Base price', render: (row) => <span className="font-medium text-ink text-right">{inr(row.base_price_paise)}</span>, className: 'text-right' },
    { key: 'tax', header: 'Tax %', render: (row) => <span className="text-xs text-muted text-right">{row.tax_rate_pct}%</span>, className: 'text-right' },
    {
      key: 'variants', header: 'Variants', render: (row) => <span className="text-xs text-muted">{row.variants.map((v) => v.name).join(', ') || '—'}</span>,
    },
    {
      key: 'active', header: 'Active', render: (row) => <Badge tone={row.is_active ? 'bg-emerald-50 text-emerald-700 ring-emerald-200' : 'bg-slate-100 text-slate-600 ring-slate-200'}>{row.is_active ? 'Yes' : 'No'}</Badge>,
    },
    {
      key: 'actions', header: '', className: 'text-right',
      render: (row) => (
        <div className="flex justify-end gap-1">
          {can('catalog.write') && <button onClick={() => { if (confirm(`Deactivate "${row.name}"?`)) deactivateProduct.mutate(row.id); }} className="rounded-md p-1.5 text-muted hover:bg-rose-50 hover:text-rose-600" title="Deactivate"><Trash2 size={15} /></button>}
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title="Catalog" subtitle="Manage products, categories and add-on groups for the counter menu." />
      <Tabs value={activeTab} onValueChange={setActiveTab as any} className="mb-5">
        <Tab value="products">Products</Tab>
        <Tab value="categories">Categories</Tab>
        <Tab value="addons">Add-on groups</Tab>
      </Tabs>

      {activeTab === 'products' && (
        <>
          <div className="mb-4 flex justify-between">
            <CardHeader title={`Products (${prodList.length})`} action={can('catalog.write') && <Button variant="primary" onClick={() => { setProdOpen(true); setProdCategory(''); setProdName(''); setProdDesc(''); setProdPrice(''); setProdTax('0'); setProdHsn(''); setProdSku(''); setProdBarcode(''); setProdVariants([emptyVariant()]); setProdGroupIds([]); }}><Plus size={15} /> Add product</Button>} />
          </div>
          <Card>
            {prodList.length === 0 ? <div className="p-12 text-center text-sm text-muted">No products yet.</div> : (
              <DataTable columns={columns} rows={prodList} empty="No products yet." />
            )}
          </Card>
        </>
      )}

      {activeTab === 'categories' && (
        <>
          <CardHeader title={`Categories (${catList.length})`} action={can('catalog.write') && <Button variant="primary" onClick={() => setCatOpen(true)}><Plus size={15} /> Add category</Button>} />
          <div className="mt-4 space-y-3">
            {catList.map((category) => (
              <div key={category.id} className="flex items-center justify-between px-5 py-3 border-b border-line">
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold text-xs shadow-sm`} style={{ background: category.color, color: '#ffffff' }}>{category.name.slice(0, 2).toUpperCase()}</div>
                  <div>
                    <div className="font-medium text-ink">{category.name}</div>
                    <div className="text-[11px] text-muted">Sort order {category.sort_order}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={category.is_active ? 'bg-emerald-50 text-emerald-700 ring-emerald-200' : 'bg-slate-100 text-slate-600 ring-slate-200'}>{category.is_active ? 'Active' : 'Inactive'}</Badge>
                  {can('catalog.write') && <button onClick={() => deactivateCategory.mutate(category.id)} className="text-muted hover:bg-rose-50 rounded-md p-1" title="Deactivate"><X size={14} /></button>}
                </div>
              </div>
            ))}
            {catList.length === 0 && <div className="px-5 py-8 text-center text-sm text-muted">No categories yet.</div>}
          </div>
          <Modal open={catOpen} onClose={() => setCatOpen(false)} title="New category" width="max-w-md">
            <form onSubmit={(e) => { e.preventDefault(); createCategory.mutate(); }} className="space-y-4">
              <Field label="Name"><Input value={catName} onChange={(e) => setCatName(e.target.value)} required /></Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Color"><Input type="color" value={catColor} onChange={(e) => setCatColor(e.target.value)} className="h-10 w-full rounded-lg border border-line bg-transparent px-0 py-0 cursor-pointer" /></Field>
                <Field label="Sort order"><Input type="number" value={catSort} onChange={(e) => setCatSort(e.target.value)} /></Field>
              </div>
              <div className="flex justify-end gap-2 border-t border-line pt-4"><Button type="button" onClick={() => setCatOpen(false)}>Cancel</Button><Button type="submit" variant="primary" loading={createCategory.isPending}>Create category</Button></div>
            </form>
          </Modal>
        </>
      )}

      {activeTab === 'addons' && (
        <>
          <CardHeader title={`Add-on groups (${addonList.length})`} action={can('catalog.write') && <Button variant="primary" onClick={() => { setAddonOpen(true); setAddonName(''); setAddonMin('0'); setAddonMax('1'); setAddonRequired(false); setAddonOptions([]); }}><Plus size={15} /> Add group</Button>} />
          <div className="mt-4 space-y-4">
            {addonList.map((group) => (
              <div key={group.id} className="rounded-lg border border-line p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2"><div className="font-medium text-ink">{group.name}</div>{group.is_required && <Badge tone="bg-rose-50 text-rose-700 ring-rose-100">Required</Badge>}</div>
                  <span className="text-xs text-muted">{group.min_select}–{group.max_select}</span>
                </div>
                <div className="grid gap-1 text-xs text-muted">
                  {group.modifiers.map((m) => <div key={m.id} className="flex justify-between">{m.name} {m.price_paise > 0 && <span className="text-ink">(+{inr(m.price_paise)})</span>}</div>)}
                </div>
              </div>
            ))}
            {addonList.length === 0 && <div className="px-5 py-8 text-center text-sm text-muted">No add-on groups yet.</div>}
          </div>
          <Modal open={addonOpen} onClose={() => setAddonOpen(false)} title="New add-on group" width="max-w-md">
            <form onSubmit={(e) => { e.preventDefault(); createAddon.mutate(); }} className="space-y-4">
              <Field label="Name"><Input value={addonName} onChange={(e) => setAddonName(e.target.value)} required /></Field>
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Min selections"><Input type="number" min="0" value={addonMin} onChange={(e) => setAddonMin(e.target.value)} /></Field>
                <Field label="Max selections"><Input type="number" min="1" value={addonMax} onChange={(e) => setAddonMax(e.target.value)} /></Field>
                <Field label=""><label className="flex items-center gap-2"><input type="checkbox" checked={addonRequired} onChange={(e) => setAddonRequired(e.target.checked)} className="rounded border-line text-brand-600 focus:ring-brand-500" /><span className="text-sm text-ink">Required</span></label></Field>
              </div>
              <div className="border-t border-line pt-4">
                <div className="mb-2 flex items-center justify-between"><span className="font-semibold text-xs text-ink">Options</span><button type="button" onClick={addAddonOption} className="text-xs text-brand-600 hover:underline">+ Add option</button></div>
                <div className="space-y-2">
                  {addonOptions.map((option, i) => (
                    <div key={i} className="flex gap-2">
                      <Input value={option.name} onChange={(e) => { const next = [...addonOptions]; next[i].name = e.target.value; setAddonOptions(next); }} placeholder="Option name" className="flex-1" />
                      <Input type="number" value={option.price_paise / 100} onChange={(e) => { const next = [...addonOptions]; next[i].price_paise = Math.round(Number(e.target.value || 0) * 100); setAddonOptions(next); }} placeholder="0.00" className="w-24 text-right" />
                      <button type="button" onClick={() => removeAddonOption(i)} className="text-rose-600 hover:bg-rose-50 rounded-md p-1"><X size={14} /></button>
                    </div>
                  ))}
                </div>
              </div>
              <div className="flex justify-end gap-2 border-t border-line pt-4"><Button type="button" onClick={() => setAddonOpen(false)}>Cancel</Button><Button type="submit" variant="primary" loading={createAddon.isPending}>Create group</Button></div>
            </form>
          </Modal>
        </>
      )}

      <Modal open={prodOpen} onClose={() => setProdOpen(false)} title="New product" width="max-w-2xl">
        <form onSubmit={(e) => { e.preventDefault(); createProduct.mutate(); }} className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-4">
            <Field label="Category"><select value={prodCategory} onChange={(e) => setProdCategory(e.target.value)} className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm"><option value="">Select category</option>{catList.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
            <Field label="Name"><Input value={prodName} onChange={(e) => setProdName(e.target.value)} required /></Field>
            <Field label="Base price (₹)"><Input type="number" step="0.01" min="0" value={prodPrice} onChange={(e) => setProdPrice(e.target.value)} required /></Field>
            <Field label="Tax %"><Input type="number" step="0.5" min="0" max="100" value={prodTax} onChange={(e) => setProdTax(e.target.value)} /></Field>
          </div>
          <Field label="Description"><Input value={prodDesc} onChange={(e) => setProdDesc(e.target.value)} placeholder="e.g. House masala tea" /></Field>
          <Field label="HSN / SAC"><Input value={prodHsn} onChange={(e) => setProdHsn(e.target.value)} placeholder="996331" /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="SKU (optional)"><Input value={prodSku} onChange={(e) => setProdSku(e.target.value)} placeholder="CHAI-MAS" /></Field>
            <Field label="Barcode (optional)"><Input value={prodBarcode} onChange={(e) => setProdBarcode(e.target.value)} placeholder="8901234567890" /></Field>
          </div>
          <div className="border-t border-line pt-4">
            <div className="mb-2 flex items-center justify-between"><span className="font-semibold text-xs text-ink">Variants (sizes)</span><button type="button" onClick={addVariant} className="text-xs text-brand-600 hover:underline">+ Add variant</button></div>
            <div className="space-y-2">
              {prodVariants.map((variant, i) => (
                <div key={i} className="flex gap-2">
                  <Input value={variant.name} onChange={(e) => { const next = [...prodVariants]; next[i].name = e.target.value; setProdVariants(next); }} placeholder="Small" className="flex-1" />
                  <Input type="number" step="0.01" min="0" value={(variant.price_paise / 100).toFixed(2)} onChange={(e) => { const next = [...prodVariants]; next[i].price_paise = Math.round(Number(e.target.value || 0) * 100); setProdVariants(next); }} placeholder="0.00" className="w-32 text-right" />
                  <button type="button" onClick={() => removeVariant(i)} className="text-rose-600 hover:bg-rose-50 rounded-md p-1"><X size={14} /></button>
                </div>
              ))}
              {prodVariants.length === 0 && <div className="text-xs text-muted text-center py-2">Add at least one variant.</div>}
            </div>
          </div>
          <div className="border-t border-line pt-4">
            <div className="mb-2 flex items-center justify-between"><span className="font-semibold text-xs text-ink">Add-on groups</span></div>
            <div className="grid gap-2">
              {addonList.map((group) => (
                <button key={group.id} type="button" onClick={() => toggleGroup(group.id)} className={`flex items-center justify-between rounded-lg border px-3 py-2 text-sm transition ${prodGroupIds.includes(group.id) ? 'bg-brand-50 text-brand-700 border-brand-300' : 'bg-white text-ink border-line hover:bg-slate-50'}`}>
                  <span>{group.name}</span>
                  {prodGroupIds.includes(group.id) ? <span className="text-brand-700 font-semibold">✓</span> : null}
                </button>
              ))}
              {addonList.length === 0 && <div className="text-xs text-muted text-center py-2">No add-on groups created yet.</div>}
            </div>
          </div>
          <div className="flex justify-end gap-2 border-t border-line pt-4"><Button type="button" onClick={() => setProdOpen(false)}>Cancel</Button><Button type="submit" variant="primary" loading={createProduct.isPending}>Create product</Button></div>
        </form>
      </Modal>
    </div>
  );
}
