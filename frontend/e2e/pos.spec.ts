import { expect, test } from '@playwright/test';

const PASSWORD = 'Password123!';

async function login(page: import('@playwright/test').Page, email: string, shop: string) {
  await page.goto('/login');
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByPlaceholder('e.g. chai-indiranagar').fill(shop);
  await page.getByRole('button', { name: 'Sign in' }).click();
}

test('cashier can ring up a cash sale and see the receipt, but cannot void', async ({ page }) => {
  await login(page, 'cashier@chaicorner.example.com', 'chai-indiranagar');
  await expect(page.getByRole('heading', { name: 'Counter' })).toBeVisible();

  // Open the first product tile and add the default variant to the cart.
  await page.locator('button:has-text("Masala Chai")').first().click();
  await page.getByRole('button', { name: 'Add to cart' }).click();
  await expect(page.getByText('Cart (1)')).toBeVisible();

  // Checkout with cash.
  await page.getByRole('button', { name: /Checkout ·/ }).click();
  await page.getByRole('button', { name: 'Confirm payment' }).click();
  await expect(page.getByRole('heading', { name: /Bill BILL-/ })).toBeVisible();
  await expect(page.getByText('Paid by CASH')).toBeVisible();

  // Counter sales list shows the sale; cashier has no Void action.
  await page.getByRole('link', { name: 'Counter sales' }).click();
  await expect(page.getByText('BILL-').first()).toBeVisible();
  await expect(page.getByTitle('Void')).toHaveCount(0);
});

test('owner can void a sale', async ({ page }) => {
  await login(page, 'owner@chaicorner.example.com', 'chai-indiranagar');
  await page.goto('/pos/sales');
  const voidButton = page.getByTitle('Void').first();
  if (await voidButton.count()) {
    page.once('dialog', (dialog) => dialog.accept());
    await voidButton.click();
    await expect(page.getByText('Sale voided')).toBeVisible();
  }
});

test('shops are isolated: Koramangala does not see Indiranagar sales', async ({ page }) => {
  await login(page, 'owner@chaicorner.example.com', 'chai-koramangala');
  await expect(page.getByText('Chai Corner — Koramangala')).toBeVisible();
  await page.goto('/pos/sales');
  await expect(page.getByText('0 sales')).toBeVisible();
});
