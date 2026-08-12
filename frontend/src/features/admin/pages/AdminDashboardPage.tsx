import { useMemo } from 'react'
import { BarChart3, Boxes, Download, ShoppingCart, Users } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { tw } from '../../../lib/tailwind-styles'
import { Metric } from '../components/Metric'
import { OrderRows } from '../components/OrderRows'
import { AdminErrorState } from '../components/AdminErrorState'
import { useAdminData } from '../hooks/useAdminData'
import { exportAdminReport } from '../utils/exportAdminReport'

export function AdminDashboardPage() {
    const data = useAdminData();
    const revenue = data.orderList
        .filter((order) => order.status === 'completed')
        .reduce((total, order) => total + Number(order.total), 0);
    const chartData = useMemo(() => {
        const days = Array.from({ length: 7 }, (_, offset) => {
            const date = new Date();
            date.setDate(date.getDate() - (6 - offset));
            return { key: date.toISOString().slice(0, 10), day: date.toLocaleDateString(undefined, { weekday: 'short' }), revenue: 0 };
        });
        data.orderList.forEach((order) => {
            const row = days.find((day) => day.key === order.created_at.slice(0, 10));
            if (row)
                row.revenue += Number(order.total);
        });
        return days;
    }, [data.orderList]);
    if (data.isError)
        return <AdminErrorState resource="dashboard data" />;
    const inStock = data.productList.filter((product) => product.inventory_quantity > 5).length;
    const lowStock = data.productList.filter((product) => product.inventory_quantity > 0 && product.inventory_quantity <= 5);
    const outOfStock = data.productList.filter((product) => product.inventory_quantity === 0).length;
    return (<main className={tw("admin-page")}>
      <div className={tw("admin-title-row")}>
        <div><h1>Dashboard</h1><p>{new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })} &nbsp;-&nbsp; Store overview</p></div>
        <button type="button" onClick={() => void exportAdminReport({ kind: 'orders', rows: data.orderList })}><Download size={18}/>Export report</button>
      </div>
      <section className={tw("admin-stats")}>
        <Metric label="Revenue" value={`$${revenue.toLocaleString()}`} icon={BarChart3}/>
        <Metric label="Orders" value={String(data.orderList.length)} icon={ShoppingCart}/>
        <Metric label="Customers" value={String(data.userList.filter((user) => user.is_customer && !user.is_staff).length)} icon={Users}/>
        <Metric label="Products" value={String(data.productList.length)} icon={Boxes} note={`${lowStock.length} low stock`}/>
      </section>
      <section className={tw("dashboard-grid")}>
        <article className={tw("admin-panel revenue-panel")}>
          <div className={tw("panel-heading")}><h2>Revenue overview</h2><span>Last 7 days</span></div>
          <div className={tw("revenue-chart")}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid vertical={false} stroke="#e5eaf1"/>
                <XAxis dataKey="day" axisLine={false} tickLine={false}/>
                <YAxis hide/>
                <Tooltip formatter={(value) => `$${Number(value).toFixed(2)}`}/>
                <Bar dataKey="revenue" fill="#0869f7" radius={[5, 5, 0, 0]}/>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </article>
        <article className={tw("inventory-panel")}>
          <h2>Inventory health</h2>
          <dl><div><dt><i className={tw("green")}/>In stock</dt><dd>{inStock}</dd></div><div><dt><i className={tw("amber")}/>Low stock</dt><dd>{lowStock.length}</dd></div><div><dt><i className={tw("red")}/>Out of stock</dt><dd>{outOfStock}</dd></div></dl>
        </article>
        <article className={tw("admin-panel recent-orders")}>
          <div className={tw("panel-heading")}><h2>Recent orders</h2><NavLink to="/admin/orders">View all</NavLink></div>
          <OrderRows orders={data.orderList.slice(0, 4)} compact/>
        </article>
        <article className={tw("admin-panel low-stock")}>
          <div className={tw("panel-heading")}><h2>Low stock</h2><NavLink to="/admin/products">Manage</NavLink></div>
          {lowStock.length ? lowStock.map((product) => <div key={product.id}><strong>{product.name}</strong><span>{product.inventory_quantity} left</span></div>) : <p>No low-stock products.</p>}
        </article>
      </section>
    </main>);
}
