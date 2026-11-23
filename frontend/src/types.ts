export type Item = {
  id?: string;
  description: string;
  hsn_sac?: string | null;
  qty: number;
  unit_price_paise: number;
  discount_paise: number;
  tax_rate_pct: number;
  taxable_paise?: number;
  cgst_paise?: number;
  sgst_paise?: number;
  igst_paise?: number;
  tax_paise?: number;
  total_paise?: number;
  position?: number;
  product_id?: string | null;
  variant_id?: string | null;
  modifiers?: { id: string; name: string; price_paise: number }[] | null;
};

export type Address = {
  id?: string;
  type: string;
  line1: string;
  line2?: string | null;
  city: string;
  state_code: string;
  pincode: string;
  is_default: boolean;
};

export type Customer = {
  id: string;
  legal_name: string;
  display_name: string;
  gstin?: string | null;
  tax_type: string;
  state_code: string;
  email?: string | null;
  phone?: string | null;
  payment_terms_days: number;
  credit_limit_paise?: number | null;
  status: string;
  notes?: string | null;
  created_at?: string | null;
  addresses: Address[];
  outstanding_paise: number;
};

export type Quote = {
  id: string;
  customer_id: string;
  number?: string | null;
  status: string;
  issue_date: string;
  valid_until?: string | null;
  subtotal_paise: number;
  discount_paise: number;
  tax_paise: number;
  total_paise: number;
  currency: string;
  notes?: string | null;
  terms?: string | null;
  converted_invoice_id?: string | null;
  version: number;
  created_at: string;
  items: Item[];
};

export type Invoice = {
  id: string;
  customer_id: string;
  quote_id?: string | null;
  number?: string | null;
  status: string;
  issue_date: string;
  due_date: string;
  subtotal_paise: number;
  discount_paise: number;
  tax_paise: number;
  round_off_paise: number;
  total_paise: number;
  paid_paise: number;
  credited_paise: number;
  balance_paise: number;
  currency: string;
  notes?: string | null;
  terms?: string | null;
  tax_mode: string;
  place_of_supply?: string | null;
  channel?: string | null;
  pos_meta?: Record<string, unknown> | null;
  version: number;
  created_at: string;
  items: Item[];
};

export type Allocation = { id?: string; invoice_id: string; amount_paise: number };

export type Payment = {
  id: string;
  customer_id: string;
  number?: string | null;
  amount_paise: number;
  allocated_paise: number;
  method: string;
  provider?: string | null;
  provider_ref?: string | null;
  status: string;
  paid_at?: string | null;
  reference_no?: string | null;
  notes?: string | null;
  created_at: string;
  allocations: Allocation[];
};

export type CreditNote = {
  id: string;
  customer_id: string;
  invoice_id?: string | null;
  number?: string | null;
  reason: string;
  status: string;
  subtotal_paise: number;
  tax_paise: number;
  total_paise: number;
  applied_paise: number;
  tax_mode: string;
  cgst_paise: number;
  sgst_paise: number;
  igst_paise: number;
  refund_mode: string;
  created_at: string;
};

export type Schedule = {
  id: string;
  customer_id: string;
  name: string;
  frequency: string;
  interval: number;
  start_date: string;
  end_date?: string | null;
  next_run_at: string;
  status: string;
  last_invoice_id?: string | null;
  last_period?: string | null;
  created_at: string;
};

export type Audit = {
  id: string;
  actor_id?: string | null;
  actor_type: string;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  ip?: string | null;
  created_at: string;
};

export type Tenant = {
  id: string;
  name: string;
  slug: string;
  legal_name?: string | null;
  gstin?: string | null;
  state_code?: string | null;
  address_line1?: string | null;
  city?: string | null;
  pincode?: string | null;
  settings: Record<string, unknown>;
};

// ---------- Catalog ----------

export type Category = {
  id: string;
  name: string;
  color: string;
  sort_order: number;
  is_active: boolean;
  created_at?: string | null;
};

export type Variant = {
  id: string;
  name: string;
  price_paise: number;
  is_default: boolean;
  sort_order: number;
  is_active: boolean;
};

export type Modifier = {
  id: string;
  name: string;
  price_paise: number;
  sort_order: number;
  is_active: boolean;
};

export type ModifierGroup = {
  id: string;
  name: string;
  min_select: number;
  max_select: number;
  is_required: boolean;
  sort_order: number;
  is_active: boolean;
  modifiers: Modifier[];
};

export type Product = {
  id: string;
  category_id: string;
  name: string;
  description?: string | null;
  base_price_paise: number;
  tax_rate_pct: number;
  hsn_sac?: string | null;
  sku?: string | null;
  barcode?: string | null;
  sort_order: number;
  is_active: boolean;
  created_at?: string | null;
  variants: Variant[];
  modifier_group_ids: string[];
};

export type MenuProduct = {
  id: string;
  category_id: string;
  name: string;
  description?: string | null;
  base_price_paise: number;
  tax_rate_pct: number;
  hsn_sac?: string | null;
  sku?: string | null;
  barcode?: string | null;
  sort_order: number;
  variants: Variant[];
  modifier_groups: ModifierGroup[];
};

export type MenuCategory = {
  id: string;
  name: string;
  color: string;
  sort_order: number;
  products: MenuProduct[];
};

// ---------- POS ----------

export type PosSaleItem = {
  product_id: string;
  variant_id?: string | null;
  modifier_ids: string[];
  qty: number;
  discount_paise?: number;
  discount_pct?: number;
};

export type PosPayment = {
  method: 'CASH' | 'UPI' | 'CARD';
  amount_paise?: number | null;
  tendered_paise?: number | null;
  reference_no?: string | null;
};

export type PosSale = {
  id: string;
  number?: string | null;
  status: string;
  issue_date: string;
  total_paise: number;
  discount_paise: number;
  tax_paise: number;
  subtotal_paise: number;
  round_off_paise: number;
  paid_paise: number;
  balance_paise: number;
  pos_meta: {
    method?: string;
    tendered_paise?: number;
    change_paise?: number;
    reference_no?: string | null;
    cashier?: string | null;
    voided?: boolean;
    refunded_paise?: number;
    payments?: Array<{ method: string; amount_paise: number; tendered_paise: number; change_paise: number; reference_no?: string | null }>;
    refunds?: Array<{ amount_paise: number; method: string; reason: string; at: string }>;
  } | null;
  channel?: string | null;
  items: Item[];
  created_at?: string | null;
};

export type DailyReport = {
  date: string;
  sales_count: number;
  gross_paise: number;
  discount_paise: number;
  tax_paise: number;
  refunded_paise?: number;
  average_bill_paise: number;
  payment_mix: Record<string, { count: number; amount_paise: number }>;
  top_items: Array<{ description: string; qty: number; amount_paise: number }>;
  hourly: Array<{ hour: number; sales: number; amount_paise: number }>;
};

export type RangeReport = Omit<DailyReport, 'date'> & {
  from: string;
  to: string;
  days: Array<{ date: string; sales: number; amount_paise: number }>;
  previous: { from: string; to: string; sales_count: number; gross_paise: number };
  gross_delta_paise: number;
  sales_delta: number;
};

export type HeldOrder = {
  id: string;
  label?: string | null;
  cart: Record<string, unknown>;
  created_at?: string | null;
};

export type ShiftSummary = {
  id: string;
  status: string;
  opened_at?: string | null;
  closed_at?: string | null;
  opening_float_paise: number;
  cash_sales_paise: number;
  refunds_paise: number;
  cash_in_paise: number;
  cash_out_paise: number;
  expected_cash_paise: number | null;
  closing_count_paise?: number | null;
  variance_paise?: number | null;
  movement_count: number;
  blind_close: boolean;
};

export type ShopSummary = {
  tenant_id: string;
  tenant_name?: string | null;
  slug?: string | null;
  today_sales: number;
  today_gross_paise: number;
  role?: string | null;
};
