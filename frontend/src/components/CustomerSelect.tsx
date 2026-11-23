import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../lib/api';
import { Select } from './ui';
import type { Customer } from '../types';

export function useCustomers() {
  return useQuery({
    queryKey: ['customers', 'all'],
    queryFn: async () => (await apiGet<Customer[]>('/customers?limit=200')).data,
  });
}

export function CustomerSelect({ value, onChange, placeholder = 'Select a customer' }: { value: string; onChange: (value: string) => void; placeholder?: string }) {
  const customers = useCustomers();
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{placeholder}</option>
      {(customers.data || []).map((customer) => (
        <option key={customer.id} value={customer.id}>{customer.display_name}{customer.gstin ? ` · ${customer.gstin}` : ''}</option>
      ))}
    </Select>
  );
}
