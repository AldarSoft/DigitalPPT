import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '../../../lib/api'

export function useAdminData() {
    const products = useQuery({ queryKey: ['admin-products'], queryFn: () => api.products('ordering=-created_at&page_size=100') });
    const orders = useQuery({ queryKey: ['admin-orders'], queryFn: () => api.orders('ordering=-created_at&page_size=100') });
    const users = useQuery({ queryKey: ['admin-users'], queryFn: () => api.users('page_size=100') });
    return {
        products,
        orders,
        users,
        productList: products.data ? unwrap(products.data) : [],
        orderList: orders.data ? unwrap(orders.data) : [],
        userList: users.data ? unwrap(users.data) : [],
        isError: products.isError || orders.isError || users.isError,
    };
}
