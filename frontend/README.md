# Digital PTT Frontend

React 19 and TypeScript storefront for the Digital PTT Django backend.

## Run

```powershell
npm.cmd install
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

The backend should run at `http://127.0.0.1:8000`.

## Checks

```powershell
npm.cmd run lint
.\node_modules\.bin\tsc.cmd --noEmit
npm.cmd run build
```

## Implemented

- Storefront, catalog, product details, cart, and pending-order checkout
- Customer authentication and account management
- Staff products, orders, customers, promotions, inventory, and analytics

## Not Implemented

- Payment
- Secure promotion redemption at checkout
- Tax and shipping calculations
- Quote/content frontend administration
- Automated frontend test suite
- Production deployment configuration

Full status: [`../docsai/frontend/IMPLEMENTATION_STATUS.md`](../docsai/frontend/IMPLEMENTATION_STATUS.md)

